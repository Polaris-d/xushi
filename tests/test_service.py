"""任务服务测试。"""

from datetime import UTC, datetime

from xushi.config import Settings
from xushi.models import FollowUpPolicy, RunCallback, Schedule, TaskCreate
from xushi.service import XushiService


def test_manual_trigger_creates_a_run(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    task = service.create_task(
        TaskCreate(
            title="生成日报",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                timezone="UTC",
            ),
            action={"type": "reminder", "payload": {"message": "生成日报"}},
        )
    )

    run = service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))

    assert run.task_id == task.id
    assert run.status == "succeeded"


def test_create_task_reuses_idempotency_key(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    request = TaskCreate(
        title="生成日报",
        schedule=Schedule(
            kind="one_shot",
            run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
            timezone="UTC",
        ),
        action={"type": "reminder", "payload": {"message": "生成日报"}},
        idempotency_key="agent-retry-1",
    )

    first = service.create_task(request)
    second = service.create_task(request)

    assert second.id == first.id
    assert len(service.list_tasks()) == 1


def test_confirm_run_marks_pending_run_succeeded(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    task = service.create_task(
        TaskCreate(
            title="饭后吃药",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                timezone="UTC",
            ),
            action={"type": "reminder", "payload": {"message": "饭后吃药"}},
            follow_up_policy=FollowUpPolicy(requires_confirmation=True),
        )
    )
    run = service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))

    confirmed = service.confirm_run(run.id, now=datetime(2026, 5, 9, 12, 3, tzinfo=UTC))

    assert confirmed is not None
    assert confirmed.status == "succeeded"
    assert confirmed.confirmed_at == datetime(2026, 5, 9, 12, 3, tzinfo=UTC)


def test_process_follow_ups_creates_follow_up_run_when_confirmation_is_late(tmp_path) -> None:
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
            follow_up_policy=FollowUpPolicy(
                requires_confirmation=True,
                grace_period="PT5M",
                interval="PT10M",
                max_attempts=2,
            ),
        )
    )
    run = service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))

    follow_ups = service.process_follow_ups(now=datetime(2026, 5, 9, 12, 6, tzinfo=UTC))

    assert len(follow_ups) == 1
    assert follow_ups[0].task_id == task.id
    assert follow_ups[0].origin_run_id == run.id
    assert follow_ups[0].status == "following_up"
    assert follow_ups[0].follow_up_attempts == 1


def test_process_follow_ups_does_not_repeat_same_attempt(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    task = service.create_task(
        TaskCreate(
            title="吃药",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                timezone="UTC",
            ),
            action={"type": "reminder", "payload": {"message": "吃药"}},
            follow_up_policy=FollowUpPolicy(
                requires_confirmation=True,
                grace_period="PT5M",
                interval="PT10M",
                max_attempts=2,
            ),
        )
    )
    service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))

    first = service.process_follow_ups(now=datetime(2026, 5, 9, 12, 6, tzinfo=UTC))
    second = service.process_follow_ups(now=datetime(2026, 5, 9, 12, 7, tzinfo=UTC))

    assert len(first) == 1
    assert second == []


def test_callback_run_updates_final_status_and_result(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    task = service.create_task(
        TaskCreate(
            title="生成周报",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                timezone="UTC",
            ),
            action={"type": "reminder", "payload": {"message": "生成周报"}},
            follow_up_policy=FollowUpPolicy(requires_confirmation=True),
        )
    )
    run = service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))

    updated = service.callback_run(
        run.id,
        RunCallback(
            status="succeeded",
            result={"agent_run_id": "remote_123", "summary": "已完成"},
            finished_at=datetime(2026, 5, 9, 12, 5, tzinfo=UTC),
        ),
    )

    assert updated is not None
    assert updated.status == "succeeded"
    assert updated.confirmed_at == datetime(2026, 5, 9, 12, 5, tzinfo=UTC)
    assert updated.result["agent_run_id"] == "remote_123"
    assert updated.result["summary"] == "已完成"


def test_callback_run_marks_failure_and_keeps_error(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    task = service.create_task(
        TaskCreate(
            title="同步文件",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                timezone="UTC",
            ),
            action={"type": "reminder", "payload": {"message": "同步文件"}},
            follow_up_policy=FollowUpPolicy(requires_confirmation=True),
        )
    )
    run = service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))

    updated = service.callback_run(run.id, RunCallback(status="failed", error="agent failed"))

    assert updated is not None
    assert updated.status == "failed"
    assert updated.error == "agent failed"


def test_completion_anchor_waits_for_confirmation_before_next_run(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    service.create_task(
        TaskCreate(
            title="久坐提醒",
            schedule=Schedule(
                kind="recurring",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                rrule="FREQ=HOURLY",
                timezone="UTC",
                anchor="completion",
            ),
            action={"type": "reminder", "payload": {"message": "起来活动一下"}},
            follow_up_policy=FollowUpPolicy(requires_confirmation=True),
        )
    )
    first_runs = service.tick(now=datetime(2026, 5, 9, 12, 1, tzinfo=UTC))
    unconfirmed_runs = service.tick(now=datetime(2026, 5, 9, 13, 1, tzinfo=UTC))
    service.confirm_run(first_runs[0].id, now=datetime(2026, 5, 9, 12, 10, tzinfo=UTC))

    before_completion_interval = service.tick(now=datetime(2026, 5, 9, 13, 5, tzinfo=UTC))
    after_completion_interval = service.tick(now=datetime(2026, 5, 9, 13, 11, tzinfo=UTC))

    assert len(first_runs) == 1
    assert unconfirmed_runs == []
    assert before_completion_interval == []
    assert len(after_completion_interval) == 1
    assert after_completion_interval[0].scheduled_for == datetime(2026, 5, 9, 13, 10, tzinfo=UTC)
