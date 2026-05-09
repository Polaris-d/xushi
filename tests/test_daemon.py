"""daemon 后台循环测试。"""

from datetime import UTC, datetime

from xushi.config import Settings
from xushi.models import Schedule, TaskCreate
from xushi.runtime import run_scheduler_once
from xushi.service import XushiService


def test_run_scheduler_once_triggers_due_tasks_and_follow_ups(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    task = service.create_task(
        TaskCreate(
            title="到点提醒",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                timezone="UTC",
            ),
            action={"type": "reminder", "payload": {"message": "到点了"}},
        )
    )

    runs = run_scheduler_once(service, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))

    assert len(runs) == 1
    assert runs[0].task_id == task.id
