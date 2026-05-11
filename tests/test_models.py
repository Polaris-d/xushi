"""任务结构化契约测试。"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from xushi.models import Executor, QuietPolicy, QuietWindow, Schedule, TaskCreate


def test_schedule_requires_timezone() -> None:
    with pytest.raises(ValidationError):
        Schedule(kind="one_shot", run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))


def test_recurring_schedule_requires_rrule() -> None:
    with pytest.raises(ValidationError):
        Schedule(kind="recurring", run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC), timezone="UTC")


def test_schedule_rejects_naive_datetime_fields() -> None:
    cases = [
        {
            "kind": "one_shot",
            "run_at": datetime(2026, 5, 9, 12, 0),
            "timezone": "Asia/Shanghai",
        },
        {
            "kind": "recurring",
            "run_at": datetime(2026, 5, 9, 12, 0),
            "rrule": "FREQ=DAILY",
            "timezone": "Asia/Shanghai",
        },
        {
            "kind": "window",
            "window_start": datetime(2026, 5, 9, 12, 0),
            "window_end": datetime(2026, 5, 9, 13, 0, tzinfo=UTC),
            "timezone": "Asia/Shanghai",
        },
        {
            "kind": "deadline",
            "deadline": datetime(2026, 5, 9, 18, 0),
            "timezone": "Asia/Shanghai",
        },
    ]

    for data in cases:
        with pytest.raises(ValidationError, match="timezone-aware"):
            Schedule(**data)


def test_quiet_policy_accepts_multiple_windows() -> None:
    policy = QuietPolicy(
        enabled=True,
        timezone="Asia/Shanghai",
        windows=[
            QuietWindow(start="12:30", end="14:00", days="workdays"),
            QuietWindow(start="22:30", end="08:00"),
        ],
    )

    assert len(policy.windows) == 2
    assert policy.windows[0].start_minutes() == 750
    assert policy.windows[1].end_minutes() == 480


def test_quiet_window_rejects_same_start_and_end() -> None:
    with pytest.raises(ValidationError):
        QuietWindow(start="08:00", end=8)


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


def test_executor_rejects_command_kind() -> None:
    with pytest.raises(ValidationError):
        Executor(
            id="legacy_command",
            kind="command",
            name="Legacy Command",
            config={"command": "echo hi"},
        )
