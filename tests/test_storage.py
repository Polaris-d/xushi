"""SQLite 存储资源释放测试。"""

import sqlite3
from datetime import UTC, datetime

from xushi.config import Settings
from xushi.models import Action, Delivery, DeliveryStatus, Run, RunStatus, Schedule, TaskCreate
from xushi.service import XushiService
from xushi.storage import SQLiteStore


def test_sqlite_connections_are_closed_after_operations(tmp_path) -> None:
    database_path = tmp_path / "xushi.db"
    service = XushiService(Settings(database_path=database_path, api_token="test-token"))
    task = service.create_task(
        TaskCreate(
            title="释放句柄",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                timezone="UTC",
            ),
            action={"type": "reminder", "payload": {"message": "释放句柄"}},
        )
    )
    service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))

    database_path.unlink()

    assert not database_path.exists()


def test_sqlite_schema_does_not_store_executor_configuration(tmp_path) -> None:
    database_path = tmp_path / "xushi.db"

    XushiService(Settings(database_path=database_path, api_token="test-token"))

    with sqlite3.connect(database_path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'executors'"
        ).fetchone()

    assert row is None


def test_sqlite_schema_adds_query_columns_and_indexes(tmp_path) -> None:
    database_path = tmp_path / "xushi.db"

    SQLiteStore(database_path)

    with sqlite3.connect(database_path) as conn:
        task_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
        }
        run_columns = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
        index_names = {
            row[1] for row in conn.execute("PRAGMA index_list(tasks)").fetchall()
        } | {row[1] for row in conn.execute("PRAGMA index_list(runs)").fetchall()} | {
            row[1] for row in conn.execute("PRAGMA index_list(deliveries)").fetchall()
        }

    assert {"idempotency_key", "idempotency_hash"} <= task_columns
    assert {"origin_run_id", "confirmed_at"} <= run_columns
    assert {
        "idx_tasks_status_created_at",
        "idx_tasks_idempotency_key",
        "idx_runs_task_status_scheduled_for",
        "idx_runs_origin_status",
        "idx_deliveries_status_deliver_at",
        "idx_deliveries_run_status",
    } <= index_names


def test_sqlite_store_migrates_legacy_task_idempotency_columns(tmp_path) -> None:
    database_path = tmp_path / "xushi.db"
    task = TaskCreate(
        title="生成日报",
        schedule=Schedule(
            kind="one_shot",
            run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
            timezone="UTC",
        ),
        action={"type": "reminder", "payload": {"message": "生成日报"}},
        idempotency_key="legacy-key",
    ).to_task("task_legacy")
    with sqlite3.connect(database_path) as conn:
        conn.execute(
            """
            CREATE TABLE tasks (
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
            INSERT INTO tasks (id, payload, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                task.id,
                task.model_dump_json(),
                task.status,
                task.created_at.isoformat(),
                task.updated_at.isoformat(),
            ),
        )

    store = SQLiteStore(database_path)

    with sqlite3.connect(database_path) as conn:
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    migrated = store.get_task_by_idempotency_key("legacy-key")

    assert user_version >= 1
    assert migrated is not None
    assert migrated.id == "task_legacy"


def test_sqlite_store_query_helpers_return_targeted_rows(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "xushi.db")
    task = TaskCreate(
        title="喝水",
        schedule=Schedule(
            kind="one_shot",
            run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
            timezone="UTC",
        ),
        action={"type": "reminder", "payload": {"message": "喝水"}},
    ).to_task("task_1")
    store.save_task(task)
    old_run = Run(
        id="run_old",
        task_id=task.id,
        scheduled_for=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
        started_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
        status=RunStatus.PENDING_CONFIRMATION,
    )
    latest_run = Run(
        id="run_latest",
        task_id=task.id,
        scheduled_for=datetime(2026, 5, 9, 13, 0, tzinfo=UTC),
        started_at=datetime(2026, 5, 9, 13, 0, tzinfo=UTC),
        status=RunStatus.PENDING_CONFIRMATION,
    )
    follow_up = Run(
        id="run_follow",
        task_id=task.id,
        origin_run_id=latest_run.id,
        scheduled_for=datetime(2026, 5, 9, 13, 10, tzinfo=UTC),
        started_at=datetime(2026, 5, 9, 13, 10, tzinfo=UTC),
        status=RunStatus.FOLLOWING_UP,
    )
    for run in [old_run, latest_run, follow_up]:
        store.save_run(run)
    due_delivery = Delivery(
        id="delivery_due",
        run_id=latest_run.id,
        task_id=task.id,
        action=Action(type="reminder", payload={"message": "喝水"}),
        due_at=datetime(2026, 5, 9, 13, 0, tzinfo=UTC),
        deliver_at=datetime(2026, 5, 9, 13, 0, tzinfo=UTC),
        status=DeliveryStatus.DELAYED,
        created_at=datetime(2026, 5, 9, 13, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 9, 13, 0, tzinfo=UTC),
    )
    future_delivery = Delivery(
        id="delivery_future",
        run_id=latest_run.id,
        task_id=task.id,
        action=Action(type="reminder", payload={"message": "喝水"}),
        due_at=datetime(2026, 5, 9, 14, 0, tzinfo=UTC),
        deliver_at=datetime(2026, 5, 9, 14, 0, tzinfo=UTC),
        status=DeliveryStatus.DELAYED,
        created_at=datetime(2026, 5, 9, 14, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 9, 14, 0, tzinfo=UTC),
    )
    store.save_delivery(due_delivery)
    store.save_delivery(future_delivery)

    assert store.latest_pending_primary_run_for_task(task.id).id == "run_latest"
    assert store.last_primary_run_for_task(task.id).id == "run_latest"
    assert [run.id for run in store.list_follow_ups_for_origin(latest_run.id)] == [
        "run_follow"
    ]
    assert [
        delivery.id
        for delivery in store.list_due_deliveries(datetime(2026, 5, 9, 13, 5, tzinfo=UTC))
    ] == ["delivery_due"]
    assert [
        delivery.id
        for delivery in store.list_deliveries_for_run(
            latest_run.id,
            statuses={DeliveryStatus.DELAYED.value},
        )
    ] == ["delivery_due", "delivery_future"]
