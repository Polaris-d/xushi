"""SQLite 持久化层。"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from xushi.models import Delivery, Run, Task
from xushi.notifications import NotificationEvent


class SQLiteStore:
    """序时 SQLite 数据仓库。"""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    scheduled_for TEXT NOT NULL,
                    status TEXT NOT NULL
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

    def save_task(self, task: Task) -> Task:
        """保存任务。"""
        payload = task.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (id, payload, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    task.id,
                    payload,
                    task.status,
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                ),
            )
        return task

    def list_tasks(self) -> list[Task]:
        """返回所有任务。"""
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM tasks ORDER BY created_at DESC").fetchall()
        return [Task.model_validate_json(row["payload"]) for row in rows]

    def get_task(self, task_id: str) -> Task | None:
        """按 ID 获取任务。"""
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return Task.model_validate_json(row["payload"])

    def save_run(self, run: Run) -> Run:
        """保存运行记录。"""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (id, task_id, payload, scheduled_for, status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    task_id = excluded.task_id,
                    scheduled_for = excluded.scheduled_for,
                    status = excluded.status
                """,
                (
                    run.id,
                    run.task_id,
                    run.model_dump_json(),
                    run.scheduled_for.isoformat(),
                    run.status,
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

    def list_runs(self) -> list[Run]:
        """返回所有运行记录。"""
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM runs ORDER BY scheduled_for DESC").fetchall()
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
                    delivery.deliver_at.isoformat(),
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

    def list_deliveries(self) -> list[Delivery]:
        """返回所有投递计划。"""
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM deliveries ORDER BY deliver_at ASC").fetchall()
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
