"""SQLite 持久化层。"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from xushi.models import Delivery, DeliveryStatus, Run, RunStatus, Task, TaskStatus
from xushi.notifications import NotificationEvent

SCHEMA_VERSION = 1


class SQLiteStore:
    """序时 SQLite 数据仓库。"""

    def __init__(
        self,
        database_path: Path,
        *,
        journal_mode: str = "delete",
        synchronous: str = "full",
    ) -> None:
        self.database_path = database_path
        self.journal_mode = journal_mode.upper()
        self.synchronous = synchronous.upper()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        self._apply_pragmas(conn)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        """按配置应用 SQLite 连接级参数。"""
        conn.execute(f"PRAGMA journal_mode = {self.journal_mode}")
        conn.execute(f"PRAGMA synchronous = {self.synchronous}")

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    idempotency_key TEXT,
                    idempotency_hash TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    origin_run_id TEXT,
                    payload TEXT NOT NULL,
                    scheduled_for TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confirmed_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS deliveries (
                    id TEXT PRIMARY KEY,
                    run_id TEXT,
                    task_id TEXT,
                    payload TEXT NOT NULL,
                    deliver_at TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            self._ensure_schema_columns(conn)
            self._backfill_structured_columns(conn)
            self._create_indexes(conn)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _ensure_schema_columns(self, conn: sqlite3.Connection) -> None:
        """为旧库补齐结构化查询列。"""
        self._ensure_column(conn, "tasks", "idempotency_key", "TEXT")
        self._ensure_column(conn, "tasks", "idempotency_hash", "TEXT")
        self._ensure_column(conn, "runs", "origin_run_id", "TEXT")
        self._ensure_column(conn, "runs", "confirmed_at", "TEXT")

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _backfill_structured_columns(self, conn: sqlite3.Connection) -> None:
        """从 JSON payload 回填可索引列，兼容 v0 库。"""
        seen_idempotency_keys = {
            row["idempotency_key"]
            for row in conn.execute(
                "SELECT idempotency_key FROM tasks WHERE idempotency_key IS NOT NULL"
            )
        }
        for row in conn.execute(
            "SELECT id, payload FROM tasks WHERE idempotency_key IS NULL ORDER BY created_at ASC"
        ).fetchall():
            try:
                payload = json.loads(row["payload"])
            except json.JSONDecodeError:
                continue
            idempotency_key = payload.get("idempotency_key")
            if not idempotency_key or idempotency_key in seen_idempotency_keys:
                continue
            conn.execute(
                "UPDATE tasks SET idempotency_key = ? WHERE id = ?",
                (idempotency_key, row["id"]),
            )
            seen_idempotency_keys.add(idempotency_key)

        for row in conn.execute("SELECT id, payload, scheduled_for FROM runs").fetchall():
            try:
                payload = json.loads(row["payload"])
            except json.JSONDecodeError:
                continue
            conn.execute(
                """
                UPDATE runs
                SET scheduled_for = ?, origin_run_id = ?, confirmed_at = ?
                WHERE id = ?
                """,
                (
                    _payload_utc_iso(payload, "scheduled_for") or row["scheduled_for"],
                    payload.get("origin_run_id"),
                    _payload_utc_iso(payload, "confirmed_at"),
                    row["id"],
                ),
            )

        for row in conn.execute("SELECT id, payload FROM deliveries").fetchall():
            try:
                payload = json.loads(row["payload"])
            except json.JSONDecodeError:
                continue
            deliver_at = _payload_utc_iso(payload, "deliver_at")
            if deliver_at is None:
                continue
            conn.execute(
                "UPDATE deliveries SET deliver_at = ? WHERE id = ?",
                (deliver_at, row["id"]),
            )

    def _create_indexes(self, conn: sqlite3.Connection) -> None:
        """创建关键路径查询索引。"""
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_status_created_at
            ON tasks(status, created_at DESC)
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_idempotency_key
            ON tasks(idempotency_key)
            WHERE idempotency_key IS NOT NULL
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_runs_task_status_scheduled_for
            ON runs(task_id, status, scheduled_for DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_runs_origin_status
            ON runs(origin_run_id, status)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_deliveries_status_deliver_at
            ON deliveries(status, deliver_at)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_deliveries_run_status
            ON deliveries(run_id, status)
            """
        )

    def save_task(self, task: Task, *, idempotency_hash: str | None = None) -> Task:
        """保存任务。"""
        payload = task.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    id, payload, status, created_at, updated_at,
                    idempotency_key, idempotency_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    idempotency_key = excluded.idempotency_key,
                    idempotency_hash = COALESCE(
                        excluded.idempotency_hash,
                        tasks.idempotency_hash
                    )
                """,
                (
                    task.id,
                    payload,
                    task.status,
                    _utc_iso(task.created_at),
                    _utc_iso(task.updated_at),
                    task.idempotency_key,
                    idempotency_hash,
                ),
            )
        return task

    def list_tasks(
        self,
        status: TaskStatus | str | None = None,
        *,
        limit: int | None = None,
    ) -> list[Task]:
        """返回所有任务。"""
        limit_clause = "LIMIT ?" if limit is not None else ""
        limit_params = (limit,) if limit is not None else ()
        with self._connect() as conn:
            if status is None:
                rows = conn.execute(
                    f"SELECT payload FROM tasks ORDER BY created_at DESC {limit_clause}",
                    limit_params,
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    SELECT payload FROM tasks
                    WHERE status = ?
                    ORDER BY created_at DESC {limit_clause}
                    """,
                    (str(status), *limit_params),
                ).fetchall()
        return [Task.model_validate_json(row["payload"]) for row in rows]

    def list_active_tasks(self) -> list[Task]:
        """返回活跃任务。"""
        return self.list_tasks(status=TaskStatus.ACTIVE)

    def get_task(self, task_id: str) -> Task | None:
        """按 ID 获取任务。"""
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return Task.model_validate_json(row["payload"])

    def get_task_by_idempotency_key(self, idempotency_key: str) -> Task | None:
        """按幂等键获取任务。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM tasks WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        if row is None:
            return None
        return Task.model_validate_json(row["payload"])

    def get_task_idempotency_hash(self, idempotency_key: str) -> str | None:
        """按幂等键获取首次请求摘要。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT idempotency_hash FROM tasks WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        if row is None:
            return None
        return row["idempotency_hash"]

    def save_run(self, run: Run) -> Run:
        """保存运行记录。"""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    id, task_id, origin_run_id, payload,
                    scheduled_for, status, confirmed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    task_id = excluded.task_id,
                    origin_run_id = excluded.origin_run_id,
                    scheduled_for = excluded.scheduled_for,
                    status = excluded.status,
                    confirmed_at = excluded.confirmed_at
                """,
                (
                    run.id,
                    run.task_id,
                    run.origin_run_id,
                    run.model_dump_json(),
                    _utc_iso(run.scheduled_for),
                    run.status,
                    _utc_iso(run.confirmed_at),
                ),
            )
        return run

    def get_run(self, run_id: str) -> Run | None:
        """按 ID 获取运行记录。"""
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return Run.model_validate_json(row["payload"])

    def list_runs(
        self,
        *,
        task_id: str | None = None,
        status: RunStatus | str | None = None,
        limit: int | None = None,
    ) -> list[Run]:
        """返回所有运行记录。"""
        clauses: list[str] = []
        params: list[str | int] = []
        if task_id is not None:
            clauses.append("task_id = ?")
            params.append(task_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(str(status))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_clause = "LIMIT ?" if limit is not None else ""
        if limit is not None:
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT payload FROM runs {where} ORDER BY scheduled_for DESC {limit_clause}",
                tuple(params),
            ).fetchall()
        return [Run.model_validate_json(row["payload"]) for row in rows]

    def last_run_for_task(self, task_id: str) -> Run | None:
        """返回任务最近一次运行记录。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM runs WHERE task_id = ? ORDER BY scheduled_for DESC LIMIT 1",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return Run.model_validate_json(row["payload"])

    def last_primary_run_for_task(self, task_id: str) -> Run | None:
        """返回任务最近一次主运行记录。"""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload FROM runs
                WHERE task_id = ? AND origin_run_id IS NULL
                ORDER BY scheduled_for DESC
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return Run.model_validate_json(row["payload"])

    def latest_pending_primary_run_for_task(self, task_id: str) -> Run | None:
        """返回任务最近一次待确认主运行记录。"""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload FROM runs
                WHERE task_id = ?
                    AND status = ?
                    AND confirmed_at IS NULL
                    AND origin_run_id IS NULL
                ORDER BY scheduled_for DESC
                LIMIT 1
                """,
                (task_id, RunStatus.PENDING_CONFIRMATION.value),
            ).fetchone()
        if row is None:
            return None
        return Run.model_validate_json(row["payload"])

    def list_follow_ups_for_origin(self, origin_run_id: str) -> list[Run]:
        """返回某主运行记录下的跟进运行记录。"""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM runs
                WHERE origin_run_id = ?
                ORDER BY scheduled_for ASC
                """,
                (origin_run_id,),
            ).fetchall()
        return [Run.model_validate_json(row["payload"]) for row in rows]

    def list_open_runs_for_task(
        self,
        task_id: str,
        statuses: set[str],
    ) -> list[Run]:
        """返回任务下指定状态的运行记录。"""
        return self._list_runs_by_statuses("task_id = ?", (task_id,), statuses)

    def _list_runs_by_statuses(
        self,
        base_clause: str,
        base_params: tuple[str, ...],
        statuses: set[str],
    ) -> list[Run]:
        placeholders = ", ".join("?" for _ in statuses)
        params = (*base_params, *sorted(statuses))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT payload FROM runs
                WHERE {base_clause}
                    AND status IN ({placeholders})
                ORDER BY scheduled_for ASC
                """,
                params,
            ).fetchall()
        return [Run.model_validate_json(row["payload"]) for row in rows]

    def save_delivery(self, delivery: Delivery) -> Delivery:
        """保存投递计划。"""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO deliveries (id, run_id, task_id, payload, deliver_at, status)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    run_id = excluded.run_id,
                    task_id = excluded.task_id,
                    deliver_at = excluded.deliver_at,
                    status = excluded.status
                """,
                (
                    delivery.id,
                    delivery.run_id,
                    delivery.task_id,
                    delivery.model_dump_json(),
                    _utc_iso(delivery.deliver_at),
                    delivery.status,
                ),
            )
        return delivery

    def get_delivery(self, delivery_id: str) -> Delivery | None:
        """按 ID 获取投递计划。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM deliveries WHERE id = ?",
                (delivery_id,),
            ).fetchone()
        if row is None:
            return None
        return Delivery.model_validate_json(row["payload"])

    def list_deliveries(
        self,
        *,
        statuses: set[str] | None = None,
        limit: int | None = None,
    ) -> list[Delivery]:
        """返回所有投递计划。"""
        limit_clause = "LIMIT ?" if limit is not None else ""
        limit_params = (limit,) if limit is not None else ()
        with self._connect() as conn:
            if statuses:
                placeholders = ", ".join("?" for _ in statuses)
                rows = conn.execute(
                    f"""
                    SELECT payload FROM deliveries
                    WHERE status IN ({placeholders})
                    ORDER BY deliver_at ASC {limit_clause}
                    """,
                    (*tuple(sorted(statuses)), *limit_params),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT payload FROM deliveries ORDER BY deliver_at ASC {limit_clause}",
                    limit_params,
                ).fetchall()
        return [Delivery.model_validate_json(row["payload"]) for row in rows]

    def list_due_deliveries(
        self,
        now: datetime,
        statuses: set[str] | None = None,
    ) -> list[Delivery]:
        """返回已到投递时间的投递计划。"""
        delivery_statuses = statuses or {
            DeliveryStatus.PENDING.value,
            DeliveryStatus.DELAYED.value,
        }
        placeholders = ", ".join("?" for _ in delivery_statuses)
        params = (*sorted(delivery_statuses), _utc_iso(now))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT payload FROM deliveries
                WHERE status IN ({placeholders})
                    AND deliver_at <= ?
                ORDER BY deliver_at ASC
                """,
                params,
            ).fetchall()
        return [Delivery.model_validate_json(row["payload"]) for row in rows]

    def list_deliveries_for_run(
        self,
        run_id: str,
        *,
        statuses: set[str] | None = None,
    ) -> list[Delivery]:
        """返回某运行记录下的投递计划。"""
        params: list[str] = [run_id]
        status_clause = ""
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            status_clause = f"AND status IN ({placeholders})"
            params.extend(sorted(statuses))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT payload FROM deliveries
                WHERE run_id = ?
                    {status_clause}
                ORDER BY deliver_at ASC
                """,
                tuple(params),
            ).fetchall()
        return [Delivery.model_validate_json(row["payload"]) for row in rows]

    def save_notification(self, event: NotificationEvent) -> NotificationEvent:
        """保存通知事件。"""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO notifications (id, payload, created_at, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    status = excluded.status
                """,
                (event.id, event.model_dump_json(), event.created_at.isoformat(), event.status),
            )
        return event

    def list_notifications(self) -> list[NotificationEvent]:
        """返回通知事件。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM notifications ORDER BY created_at ASC"
            ).fetchall()
        return [NotificationEvent.model_validate_json(row["payload"]) for row in rows]


def dump_json(value: object) -> str:
    """稳定输出 JSON 字符串。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _utc_iso(value: datetime | None) -> str | None:
    """把结构化查询时间统一存成 UTC ISO 字符串。"""
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


def _payload_utc_iso(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    try:
        return _utc_iso(datetime.fromisoformat(value))
    except ValueError:
        return None
