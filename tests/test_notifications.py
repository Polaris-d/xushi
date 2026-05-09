"""通知投递测试。"""

from datetime import UTC, datetime

from xushi.config import Settings
from xushi.models import Schedule, TaskCreate
from xushi.service import XushiService


def test_reminder_trigger_creates_notification_event(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    task = service.create_task(
        TaskCreate(
            title="喝水",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                timezone="UTC",
            ),
            action={"type": "reminder", "payload": {"message": "喝水"}},
        )
    )

    service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))
    notifications = service.list_notifications()

    assert len(notifications) == 1
    assert notifications[0].title == "喝水"
    assert notifications[0].message == "喝水"
    assert notifications[0].channel == "system"
    assert notifications[0].status in {"delivered", "fallback_logged"}


def test_follow_up_creates_follow_up_notification_event(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    task = service.create_task(
        TaskCreate(
            title="久坐提醒",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                timezone="UTC",
            ),
            action={"type": "reminder", "payload": {"message": "起来活动一下"}},
            follow_up_policy={
                "requires_confirmation": True,
                "grace_period": "PT1M",
                "interval": "PT1M",
                "max_attempts": 2,
            },
        )
    )
    service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))

    service.process_follow_ups(now=datetime(2026, 5, 9, 12, 2, tzinfo=UTC))
    notifications = service.list_notifications()

    assert len(notifications) == 2
    assert notifications[1].kind == "follow_up"
    assert "仍未确认" in notifications[1].message
