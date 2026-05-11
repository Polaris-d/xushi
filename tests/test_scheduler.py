"""任务调度语义测试。"""

from datetime import UTC, datetime, timedelta

from xushi.models import FollowUpPolicy, MissedPolicy, Schedule, TaskCreate
from xushi.scheduler import Scheduler
from xushi.timezone import get_tzinfo


def test_expired_instant_task_does_not_catch_up() -> None:
    scheduler = Scheduler()
    task = TaskCreate(
        title="抢购",
        schedule=Schedule(
            kind="one_shot",
            run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
            timezone="UTC",
            expiry="PT30S",
            missed_policy=MissedPolicy.SKIP,
        ),
        action={"type": "agent", "executor_id": "openclaw", "payload": {"prompt": "抢购"}},
    ).to_task(task_id="task_1")

    due = scheduler.due_occurrences(
        task,
        now=datetime(2026, 5, 9, 12, 1, tzinfo=UTC),
        last_scheduled_for=None,
    )

    assert due == []


def test_recurring_task_catches_up_only_latest_missed_occurrence() -> None:
    scheduler = Scheduler()
    task = TaskCreate(
        title="吃药",
        schedule=Schedule(
            kind="recurring",
            run_at=datetime(2026, 5, 9, 8, 0, tzinfo=UTC),
            rrule="FREQ=DAILY",
            timezone="UTC",
            missed_policy=MissedPolicy.CATCH_UP_LATEST,
        ),
        action={"type": "reminder", "payload": {"message": "饭后吃药"}},
    ).to_task(task_id="task_2")

    due = scheduler.due_occurrences(
        task,
        now=datetime(2026, 5, 12, 9, 0, tzinfo=UTC),
        last_scheduled_for=datetime(2026, 5, 9, 8, 0, tzinfo=UTC),
    )

    assert due == [datetime(2026, 5, 12, 8, 0, tzinfo=UTC)]


def test_follow_up_repeats_until_confirmation_or_max_attempts() -> None:
    scheduler = Scheduler()
    policy = FollowUpPolicy(
        requires_confirmation=True,
        grace_period="PT10M",
        interval="PT5M",
        max_attempts=3,
        ask_reschedule_on_timeout=True,
    )
    scheduled_for = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)

    next_follow_up = scheduler.next_follow_up_at(
        scheduled_for=scheduled_for,
        policy=policy,
        follow_up_attempts=1,
        now=datetime(2026, 5, 9, 12, 16, tzinfo=UTC),
        confirmed_at=None,
    )

    assert next_follow_up == scheduled_for + timedelta(minutes=15)


def test_confirmation_stops_follow_up() -> None:
    scheduler = Scheduler()
    policy = FollowUpPolicy(requires_confirmation=True, interval="PT5M", max_attempts=3)

    next_follow_up = scheduler.next_follow_up_at(
        scheduled_for=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
        policy=policy,
        follow_up_attempts=0,
        now=datetime(2026, 5, 9, 12, 10, tzinfo=UTC),
        confirmed_at=datetime(2026, 5, 9, 12, 6, tzinfo=UTC),
    )

    assert next_follow_up is None


def test_window_task_triggers_at_window_start_while_window_is_open() -> None:
    scheduler = Scheduler()
    task = TaskCreate(
        title="项目会议",
        schedule=Schedule(
            kind="window",
            window_start=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
            window_end=datetime(2026, 5, 9, 13, 0, tzinfo=UTC),
            timezone="UTC",
        ),
        action={"type": "reminder", "payload": {"message": "项目会议开始"}},
    ).to_task(task_id="task_window")

    due = scheduler.due_occurrences(
        task,
        now=datetime(2026, 5, 9, 12, 5, tzinfo=UTC),
        last_scheduled_for=None,
    )

    assert due == [datetime(2026, 5, 9, 12, 0, tzinfo=UTC)]


def test_window_task_does_not_trigger_after_window_has_ended() -> None:
    scheduler = Scheduler()
    task = TaskCreate(
        title="项目会议",
        schedule=Schedule(
            kind="window",
            window_start=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
            window_end=datetime(2026, 5, 9, 13, 0, tzinfo=UTC),
            timezone="UTC",
        ),
        action={"type": "reminder", "payload": {"message": "项目会议开始"}},
    ).to_task(task_id="task_window")

    due = scheduler.due_occurrences(
        task,
        now=datetime(2026, 5, 9, 14, 0, tzinfo=UTC),
        last_scheduled_for=None,
    )

    assert due == []


def test_deadline_task_triggers_when_deadline_arrives() -> None:
    scheduler = Scheduler()
    task = TaskCreate(
        title="提交周报",
        schedule=Schedule(
            kind="deadline",
            deadline=datetime(2026, 5, 9, 18, 0, tzinfo=UTC),
            timezone="UTC",
        ),
        action={"type": "reminder", "payload": {"message": "提交周报"}},
    ).to_task(task_id="task_deadline")

    due = scheduler.due_occurrences(
        task,
        now=datetime(2026, 5, 9, 18, 1, tzinfo=UTC),
        last_scheduled_for=None,
    )

    assert due == [datetime(2026, 5, 9, 18, 0, tzinfo=UTC)]


def test_floating_task_stays_in_planning_pool_without_auto_trigger() -> None:
    scheduler = Scheduler()
    task = TaskCreate(
        title="想想旅行计划",
        schedule=Schedule(kind="floating", timezone="UTC"),
        action={"type": "reminder", "payload": {"message": "想想旅行计划"}},
    ).to_task(task_id="task_floating")

    due = scheduler.due_occurrences(
        task,
        now=datetime(2026, 5, 9, 18, 1, tzinfo=UTC),
        last_scheduled_for=None,
    )

    assert due == []


def test_asap_task_triggers_from_creation_time() -> None:
    scheduler = Scheduler()
    task = TaskCreate(
        title="尽快处理发票",
        schedule=Schedule(kind="asap", timezone="UTC"),
        action={"type": "reminder", "payload": {"message": "尽快处理发票"}},
    ).to_task(task_id="task_asap")
    task.created_at = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)

    due = scheduler.due_occurrences(
        task,
        now=datetime(2026, 5, 9, 12, 1, tzinfo=UTC),
        last_scheduled_for=None,
    )

    assert due == [datetime(2026, 5, 9, 12, 0, tzinfo=UTC)]


def test_completion_anchor_reschedules_from_confirmation_time() -> None:
    scheduler = Scheduler()
    task = TaskCreate(
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
    ).to_task(task_id="task_sedentary")

    due_before_interval = scheduler.due_occurrences(
        task,
        now=datetime(2026, 5, 9, 13, 5, tzinfo=UTC),
        last_scheduled_for=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
        last_completed_at=datetime(2026, 5, 9, 12, 10, tzinfo=UTC),
    )
    due_after_interval = scheduler.due_occurrences(
        task,
        now=datetime(2026, 5, 9, 13, 11, tzinfo=UTC),
        last_scheduled_for=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
        last_completed_at=datetime(2026, 5, 9, 12, 10, tzinfo=UTC),
    )

    assert due_before_interval == []
    assert due_after_interval == [datetime(2026, 5, 9, 13, 10, tzinfo=UTC)]


def test_completion_anchor_interprets_rrule_in_schedule_timezone_after_patch() -> None:
    scheduler = Scheduler()
    shanghai = get_tzinfo("Asia/Shanghai")
    task = TaskCreate(
        title="久坐提醒",
        schedule=Schedule(
            kind="recurring",
            run_at=datetime(2026, 5, 11, 2, 24, 39, tzinfo=UTC),
            rrule="FREQ=DAILY;BYHOUR=9,10,11,12,13,14,15,16,17,18,19,20,21,22;BYMINUTE=0",
            timezone="Asia/Shanghai",
            anchor="completion",
        ),
        action={"type": "reminder", "payload": {"message": "起来活动一下"}},
        follow_up_policy=FollowUpPolicy(requires_confirmation=True),
    ).to_task(task_id="task_sedentary")

    due = scheduler.due_occurrences(
        task,
        now=datetime(2026, 5, 11, 3, 1, tzinfo=UTC),
        last_scheduled_for=datetime(2026, 5, 11, 2, 0, tzinfo=UTC),
        last_completed_at=datetime(2026, 5, 11, 2, 32, 55, tzinfo=UTC),
    )

    assert due == [datetime(2026, 5, 11, 11, 0, tzinfo=shanghai)]


def test_workday_policy_rolls_one_shot_task_to_next_china_workday() -> None:
    scheduler = Scheduler()
    shanghai = get_tzinfo("Asia/Shanghai")
    task = TaskCreate(
        title="工作日提醒",
        schedule=Schedule(
            kind="one_shot",
            run_at=datetime(2026, 2, 17, 9, 0, tzinfo=shanghai),
            timezone="Asia/Shanghai",
            calendar_policy="workday",
        ),
        action={"type": "reminder", "payload": {"message": "工作日提醒"}},
    ).to_task(task_id="task_workday")

    due = scheduler.due_occurrences(
        task,
        now=datetime(2026, 2, 24, 9, 1, tzinfo=shanghai),
        last_scheduled_for=None,
    )

    assert due == [datetime(2026, 2, 24, 9, 0, tzinfo=shanghai)]
