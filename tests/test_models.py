"""任务结构化契约测试。"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from xushi.models import Schedule, TaskCreate


def test_schedule_requires_timezone() -> None:
    with pytest.raises(ValidationError):
        Schedule(kind="one_shot", run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))


def test_recurring_schedule_requires_rrule() -> None:
    with pytest.raises(ValidationError):
        Schedule(kind="recurring", run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC), timezone="UTC")


def test_task_create_accepts_agent_action_payload() -> None:
    task = TaskCreate(
        title="生成日报",
        schedule=Schedule(
            kind="one_shot",
            run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
            timezone="UTC",
        ),
        action={"type": "agent", "executor_id": "openclaw", "payload": {"prompt": "生成日报"}},
    )

    assert task.action.type == "agent"
    assert task.action.executor_id == "openclaw"
