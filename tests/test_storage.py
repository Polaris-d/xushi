"""SQLite 存储资源释放测试。"""

from datetime import UTC, datetime

from xushi.config import Settings
from xushi.models import Schedule, TaskCreate
from xushi.service import XushiService


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
