"""任务服务测试。"""

from datetime import UTC, datetime

import pytest

from xushi.config import Settings
from xushi.models import (
    Executor,
    FollowUpPolicy,
    QuietPolicy,
    QuietWindow,
    RunCallback,
    Schedule,
    TaskCreate,
    TaskPatch,
    TaskQuietPolicy,
)
from xushi.service import (
    IdempotencyConflictError,
    InvalidTaskConfigurationError,
    XushiService,
)
from xushi.timezone import get_tzinfo


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


def test_reminder_with_missing_executor_records_failure(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    task = service.create_task(
        TaskCreate(
            title="喝水",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                timezone="UTC",
            ),
            action={
                "type": "reminder",
                "executor_id": "missing",
                "payload": {"message": "该喝水了"},
            },
        )
    )

    run = service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))

    assert run.status == "failed"
    assert run.error == "executor not found"


def test_retry_failed_deliveries_after_executor_config_fix(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "xushi.db"
    executor = Executor(
        id="openclaw",
        kind="openclaw",
        name="OpenClaw",
        config={
            "mode": "hooks_agent",
            "webhook_url": "http://127.0.0.1:18789/hooks/agent",
            "token_env": "OPENCLAW_HOOKS_TOKEN",
        },
    )
    service = XushiService(
        Settings(database_path=database_path, api_token="test-token", executors=(executor,))
    )
    task = service.create_task(
        TaskCreate(
            title="喝水",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                timezone="UTC",
            ),
            action={
                "type": "reminder",
                "executor_id": "openclaw",
                "payload": {"message": "该喝水了"},
            },
        )
    )
    failed_run = service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))
    failed_delivery = service.list_deliveries()[0]

    requests: list[tuple[str, str]] = []

    class FakeResponse:
        status = 200

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"ok": true}'

    def fake_urlopen(req, timeout: int, context=None):
        requests.append((req.full_url, req.headers["Authorization"]))
        return FakeResponse()

    monkeypatch.setenv("OPENCLAW_HOOKS_TOKEN", "secret-token")
    monkeypatch.setattr("xushi.executors.request.urlopen", fake_urlopen)

    fixed_service = XushiService(
        Settings(database_path=database_path, api_token="test-token", executors=(executor,))
    )
    retried = fixed_service.retry_failed_deliveries(
        now=datetime(2026, 5, 9, 12, 5, tzinfo=UTC)
    )

    updated_run = fixed_service.get_run(failed_run.id)
    deliveries = fixed_service.list_deliveries()
    assert failed_run.status == "failed"
    assert failed_delivery.status == "failed"
    assert len(retried) == 1
    assert retried[0].status == "delivered"
    assert retried[0].result["retry_of"] == failed_delivery.id
    assert updated_run is not None
    assert updated_run.status == "succeeded"
    assert [delivery.status for delivery in deliveries] == ["failed", "delivered"]
    assert requests == [
        ("http://127.0.0.1:18789/hooks/agent", "Bearer secret-token"),
    ]


def test_manual_trigger_uses_executor_from_settings(tmp_path, monkeypatch) -> None:
    requests: list[tuple[str, str]] = []

    class FakeResponse:
        status = 200

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"ok": true}'

    def fake_urlopen(req, timeout: int, context=None):
        requests.append((req.full_url, req.headers["Authorization"]))
        return FakeResponse()

    monkeypatch.setattr("xushi.executors.request.urlopen", fake_urlopen)
    service = XushiService(
        Settings(
            database_path=tmp_path / "xushi.db",
            api_token="test-token",
            executors=(
                Executor(
                    id="custom-openclaw",
                    kind="openclaw",
                    name="Custom OpenClaw",
                    config={
                        "mode": "hooks_agent",
                        "webhook_url": "http://127.0.0.1:18789/hooks/agent",
                        "token": "secret-token",
                    },
                ),
            ),
        )
    )
    task = service.create_task(
        TaskCreate(
            title="喝水",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                timezone="UTC",
            ),
            action={
                "type": "reminder",
                "executor_id": "custom-openclaw",
                "payload": {"message": "该喝水了"},
            },
        )
    )

    run = service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))

    assert run.status == "succeeded"
    assert run.result["executor"] == "custom-openclaw"
    assert requests == [
        ("http://127.0.0.1:18789/hooks/agent", "Bearer secret-token"),
    ]


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


def test_create_task_rejects_idempotency_key_reuse_with_different_payload(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    first_request = TaskCreate(
        title="生成日报",
        schedule=Schedule(
            kind="one_shot",
            run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
            timezone="UTC",
        ),
        action={"type": "reminder", "payload": {"message": "生成日报"}},
        idempotency_key="agent-retry-conflict",
    )
    conflicting_request = TaskCreate(
        title="生成晚报",
        schedule=Schedule(
            kind="one_shot",
            run_at=datetime(2026, 5, 9, 18, 0, tzinfo=UTC),
            timezone="UTC",
        ),
        action={"type": "reminder", "payload": {"message": "生成晚报"}},
        idempotency_key="agent-retry-conflict",
    )

    first = service.create_task(first_request)

    with pytest.raises(IdempotencyConflictError, match="idempotency key conflict"):
        service.create_task(conflicting_request)

    assert first.title == "生成日报"
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


def test_confirm_origin_run_cancels_existing_follow_ups(tmp_path) -> None:
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
            follow_up_policy=FollowUpPolicy(
                requires_confirmation=True,
                grace_period="PT5M",
                interval="PT10M",
                max_attempts=2,
            ),
        )
    )
    origin = service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))
    service.process_follow_ups(now=datetime(2026, 5, 9, 12, 6, tzinfo=UTC))
    service.process_follow_ups(now=datetime(2026, 5, 9, 12, 16, tzinfo=UTC))

    service.confirm_run(origin.id, now=datetime(2026, 5, 9, 12, 20, tzinfo=UTC))

    follow_ups = [run for run in service.list_runs(task_id=task.id) if run.origin_run_id]
    assert {run.status for run in follow_ups} == {"cancelled"}
    assert {run.result["cancelled_reason"] for run in follow_ups} == {"confirmed_by_origin"}
    assert service.list_runs(task_id=task.id, active_only=True) == []


def test_confirm_follow_up_cancels_siblings_and_confirms_origin(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    task = service.create_task(
        TaskCreate(
            title="久坐提醒",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                timezone="UTC",
            ),
            action={"type": "reminder", "payload": {"message": "起来活动"}},
            follow_up_policy=FollowUpPolicy(
                requires_confirmation=True,
                grace_period="PT5M",
                interval="PT10M",
                max_attempts=2,
            ),
        )
    )
    origin = service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))
    first_follow_up = service.process_follow_ups(now=datetime(2026, 5, 9, 12, 6, tzinfo=UTC))[0]
    second_follow_up = service.process_follow_ups(now=datetime(2026, 5, 9, 12, 16, tzinfo=UTC))[0]

    confirmed = service.confirm_run(
        first_follow_up.id,
        now=datetime(2026, 5, 9, 12, 20, tzinfo=UTC),
    )

    stored_origin = service.get_run(origin.id)
    stored_second_follow_up = service.get_run(second_follow_up.id)
    assert confirmed is not None
    assert confirmed.status == "succeeded"
    assert stored_origin is not None
    assert stored_origin.status == "succeeded"
    assert stored_origin.result["confirmed_by_follow_up"] == first_follow_up.id
    assert stored_second_follow_up is not None
    assert stored_second_follow_up.status == "cancelled"


def test_callback_follow_up_success_confirms_origin_and_cancels_siblings(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    task = service.create_task(
        TaskCreate(
            title="久坐提醒",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                timezone="UTC",
            ),
            action={"type": "reminder", "payload": {"message": "起来活动"}},
            follow_up_policy=FollowUpPolicy(
                requires_confirmation=True,
                grace_period="PT5M",
                interval="PT10M",
                max_attempts=2,
            ),
        )
    )
    origin = service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))
    first_follow_up = service.process_follow_ups(now=datetime(2026, 5, 9, 12, 6, tzinfo=UTC))[0]
    second_follow_up = service.process_follow_ups(now=datetime(2026, 5, 9, 12, 16, tzinfo=UTC))[0]

    updated = service.callback_run(
        first_follow_up.id,
        RunCallback(
            status="succeeded",
            result={"agent_run_id": "remote_follow_up"},
            finished_at=datetime(2026, 5, 9, 12, 20, tzinfo=UTC),
        ),
    )

    stored_origin = service.get_run(origin.id)
    stored_second_follow_up = service.get_run(second_follow_up.id)
    assert updated is not None
    assert updated.status == "succeeded"
    assert stored_origin is not None
    assert stored_origin.status == "succeeded"
    assert stored_origin.result["confirmed_by_follow_up"] == first_follow_up.id
    assert stored_second_follow_up is not None
    assert stored_second_follow_up.status == "cancelled"


def test_confirm_latest_run_confirms_most_recent_primary_run(tmp_path) -> None:
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
            follow_up_policy=FollowUpPolicy(requires_confirmation=True),
        )
    )
    older = service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))
    newer = service.trigger_task(task.id, now=datetime(2026, 5, 9, 13, 0, tzinfo=UTC))

    confirmed = service.confirm_latest_run(
        task.id,
        now=datetime(2026, 5, 9, 13, 5, tzinfo=UTC),
    )

    stored_older = service.get_run(older.id)
    assert confirmed is not None
    assert confirmed.id == newer.id
    assert confirmed.status == "succeeded"
    assert stored_older is not None
    assert stored_older.status == "pending_confirmation"


def test_confirm_latest_run_uses_targeted_queries(tmp_path, monkeypatch) -> None:
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
            follow_up_policy=FollowUpPolicy(requires_confirmation=True),
        )
    )
    run = service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))

    def fail_list_runs():
        raise AssertionError("confirm_latest_run should not scan every run")

    monkeypatch.setattr(service.store, "list_runs", fail_list_runs)

    confirmed = service.confirm_latest_run(
        task.id,
        now=datetime(2026, 5, 9, 12, 5, tzinfo=UTC),
    )

    assert confirmed is not None
    assert confirmed.id == run.id


def test_delete_task_cancels_open_runs(tmp_path) -> None:
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
            follow_up_policy=FollowUpPolicy(
                requires_confirmation=True,
                grace_period="PT5M",
                max_attempts=1,
            ),
        )
    )
    origin = service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))
    follow_up = service.process_follow_ups(now=datetime(2026, 5, 9, 12, 6, tzinfo=UTC))[0]

    assert service.delete_task(task.id)

    stored_origin = service.get_run(origin.id)
    stored_follow_up = service.get_run(follow_up.id)
    assert stored_origin is not None
    assert stored_origin.status == "cancelled"
    assert stored_follow_up is not None
    assert stored_follow_up.status == "cancelled"
    assert service.list_runs(task_id=task.id, active_only=True) == []


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


def test_global_quiet_policy_delays_delivery_without_losing_run(tmp_path) -> None:
    shanghai = get_tzinfo("Asia/Shanghai")
    service = XushiService(
        Settings(
            database_path=tmp_path / "xushi.db",
            api_token="test-token",
            quiet_policy=QuietPolicy(
                enabled=True,
                timezone="Asia/Shanghai",
                windows=[QuietWindow(start="22:30", end="08:00")],
            ),
        )
    )
    task = service.create_task(
        TaskCreate(
            title="喝水",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 23, 0, tzinfo=shanghai),
                timezone="Asia/Shanghai",
            ),
            action={"type": "reminder", "payload": {"message": "喝水"}},
            follow_up_policy=FollowUpPolicy(requires_confirmation=True),
        )
    )

    run = service.trigger_task(task.id, now=datetime(2026, 5, 9, 23, 0, tzinfo=shanghai))

    deliveries = service.list_deliveries()
    assert run.status == "pending_delivery"
    assert deliveries[0].status == "delayed"
    assert deliveries[0].deliver_at.hour == 8
    assert service.list_notifications() == []

    service.tick(now=datetime(2026, 5, 10, 8, 0, tzinfo=shanghai))

    delivered_run = service.get_run(run.id)
    assert delivered_run is not None
    assert delivered_run.status == "pending_confirmation"
    assert service.list_deliveries()[0].status == "delivered"


def test_process_deliveries_uses_due_delivery_query(tmp_path, monkeypatch) -> None:
    shanghai = get_tzinfo("Asia/Shanghai")
    service = XushiService(
        Settings(
            database_path=tmp_path / "xushi.db",
            api_token="test-token",
            quiet_policy=QuietPolicy(
                enabled=True,
                timezone="Asia/Shanghai",
                windows=[QuietWindow(start="22:30", end="08:00")],
            ),
        )
    )
    task = service.create_task(
        TaskCreate(
            title="喝水",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 23, 0, tzinfo=shanghai),
                timezone="Asia/Shanghai",
            ),
            action={"type": "reminder", "payload": {"message": "喝水"}},
            follow_up_policy=FollowUpPolicy(requires_confirmation=True),
        )
    )
    run = service.trigger_task(task.id, now=datetime(2026, 5, 9, 23, 0, tzinfo=shanghai))

    def fail_list_deliveries():
        raise AssertionError("process_deliveries should not scan every delivery")

    monkeypatch.setattr(service.store, "list_deliveries", fail_list_deliveries)

    processed = service.process_deliveries(now=datetime(2026, 5, 10, 8, 0, tzinfo=shanghai))

    assert [delivery.status for delivery in processed] == ["delivered"]
    delivered_run = service.get_run(run.id)
    assert delivered_run is not None
    assert delivered_run.status == "pending_confirmation"


def test_quiet_policy_aggregates_delayed_deliveries(tmp_path) -> None:
    shanghai = get_tzinfo("Asia/Shanghai")
    service = XushiService(
        Settings(
            database_path=tmp_path / "xushi.db",
            api_token="test-token",
            quiet_policy=QuietPolicy(
                enabled=True,
                timezone="Asia/Shanghai",
                windows=[QuietWindow(start="22:30", end="08:00")],
            ),
        )
    )
    for title in ["喝水", "起立活动"]:
        task = service.create_task(
            TaskCreate(
                title=title,
                schedule=Schedule(
                    kind="one_shot",
                    run_at=datetime(2026, 5, 9, 23, 0, tzinfo=shanghai),
                    timezone="Asia/Shanghai",
                ),
                action={"type": "reminder", "payload": {"message": title}},
                follow_up_policy=FollowUpPolicy(requires_confirmation=True),
            )
        )
        service.trigger_task(task.id, now=datetime(2026, 5, 9, 23, 0, tzinfo=shanghai))

    service.process_deliveries(now=datetime(2026, 5, 10, 8, 0, tzinfo=shanghai))

    deliveries = service.list_deliveries()
    digest_deliveries = [delivery for delivery in deliveries if delivery.kind == "digest"]
    delayed_deliveries = [delivery for delivery in deliveries if delivery.kind == "reminder"]
    assert len(digest_deliveries) == 1
    assert digest_deliveries[0].status == "delivered"
    assert {delivery.status for delivery in delayed_deliveries} == {"digested"}
    assert len(service.list_notifications()) == 1


def test_quiet_policy_can_apply_only_on_workdays(tmp_path) -> None:
    shanghai = get_tzinfo("Asia/Shanghai")
    service = XushiService(
        Settings(
            database_path=tmp_path / "xushi.db",
            api_token="test-token",
            quiet_policy=QuietPolicy(
                enabled=True,
                timezone="Asia/Shanghai",
                windows=[QuietWindow(start="12:30", end="14:00", days="workdays")],
            ),
        )
    )
    task = service.create_task(
        TaskCreate(
            title="提交材料",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 11, 13, 0, tzinfo=shanghai),
                timezone="Asia/Shanghai",
            ),
            action={"type": "reminder", "payload": {"message": "提交材料"}},
        )
    )

    run = service.trigger_task(task.id, now=datetime(2026, 5, 11, 13, 0, tzinfo=shanghai))

    delivery = service.list_deliveries()[0]
    assert run.status == "pending_delivery"
    assert delivery.status == "delayed"
    assert delivery.deliver_at == datetime(2026, 5, 11, 14, 0, tzinfo=shanghai)


def test_task_can_bypass_global_quiet_policy(tmp_path) -> None:
    shanghai = get_tzinfo("Asia/Shanghai")
    service = XushiService(
        Settings(
            database_path=tmp_path / "xushi.db",
            api_token="test-token",
            quiet_policy=QuietPolicy(
                enabled=True,
                timezone="Asia/Shanghai",
                windows=[QuietWindow(start="22:30", end="08:00")],
            ),
        )
    )
    task = service.create_task(
        TaskCreate(
            title="凌晨赶飞机",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 23, 0, tzinfo=shanghai),
                timezone="Asia/Shanghai",
            ),
            action={"type": "reminder", "payload": {"message": "去机场"}},
            quiet_policy=TaskQuietPolicy(mode="bypass"),
        )
    )

    run = service.trigger_task(task.id, now=datetime(2026, 5, 9, 23, 0, tzinfo=shanghai))

    assert run.status == "succeeded"
    assert service.list_deliveries()[0].status == "delivered"


def test_confirming_pending_delivery_cancels_delayed_delivery(tmp_path) -> None:
    shanghai = get_tzinfo("Asia/Shanghai")
    service = XushiService(
        Settings(
            database_path=tmp_path / "xushi.db",
            api_token="test-token",
            quiet_policy=QuietPolicy(
                enabled=True,
                timezone="Asia/Shanghai",
                windows=[QuietWindow(start="22:30", end="08:00")],
            ),
        )
    )
    task = service.create_task(
        TaskCreate(
            title="喝水",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 23, 0, tzinfo=shanghai),
                timezone="Asia/Shanghai",
            ),
            action={"type": "reminder", "payload": {"message": "喝水"}},
        )
    )
    run = service.trigger_task(task.id, now=datetime(2026, 5, 9, 23, 0, tzinfo=shanghai))

    service.confirm_run(run.id, now=datetime(2026, 5, 9, 23, 10, tzinfo=shanghai))
    service.tick(now=datetime(2026, 5, 10, 8, 0, tzinfo=shanghai))

    updated = service.get_run(run.id)
    assert updated is not None
    assert updated.status == "succeeded"
    assert service.list_deliveries()[0].status == "cancelled"
    assert service.list_notifications() == []


def test_archiving_task_cancels_delayed_delivery(tmp_path) -> None:
    shanghai = get_tzinfo("Asia/Shanghai")
    service = XushiService(
        Settings(
            database_path=tmp_path / "xushi.db",
            api_token="test-token",
            quiet_policy=QuietPolicy(
                enabled=True,
                timezone="Asia/Shanghai",
                windows=[QuietWindow(start="22:30", end="08:00")],
            ),
        )
    )
    task = service.create_task(
        TaskCreate(
            title="喝水",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 23, 0, tzinfo=shanghai),
                timezone="Asia/Shanghai",
            ),
            action={"type": "reminder", "payload": {"message": "喝水"}},
        )
    )
    run = service.trigger_task(task.id, now=datetime(2026, 5, 9, 23, 0, tzinfo=shanghai))

    service.delete_task(task.id)
    service.tick(now=datetime(2026, 5, 10, 8, 0, tzinfo=shanghai))

    updated = service.get_run(run.id)
    assert updated is not None
    assert updated.status == "cancelled"
    assert service.list_deliveries()[0].status == "cancelled"
    assert service.list_notifications() == []


def test_task_quiet_policy_can_skip_without_global_policy(tmp_path) -> None:
    shanghai = get_tzinfo("Asia/Shanghai")
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    task = service.create_task(
        TaskCreate(
            title="非紧急事项",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 23, 0, tzinfo=shanghai),
                timezone="Asia/Shanghai",
            ),
            action={"type": "reminder", "payload": {"message": "非紧急事项"}},
            quiet_policy=TaskQuietPolicy(
                mode="skip",
                windows=[QuietWindow(start="22:30", end="08:00")],
            ),
        )
    )

    run = service.trigger_task(task.id, now=datetime(2026, 5, 9, 23, 0, tzinfo=shanghai))

    assert run.status == "cancelled"
    assert service.list_deliveries()[0].status == "skipped"
    assert service.list_notifications() == []


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


def test_complete_task_before_due_creates_manual_completion_anchor(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    task = service.create_task(
        TaskCreate(
            title="喝水",
            schedule=Schedule(
                kind="recurring",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                rrule="FREQ=HOURLY;INTERVAL=2",
                timezone="UTC",
                anchor="completion",
            ),
            action={"type": "reminder", "payload": {"message": "喝水"}},
            follow_up_policy=FollowUpPolicy(requires_confirmation=True),
        )
    )

    completed = service.complete_task(task.id, now=datetime(2026, 5, 9, 10, 40, tzinfo=UTC))
    deliveries_after_completion = service.list_deliveries()
    before_next_interval = service.tick(now=datetime(2026, 5, 9, 12, 39, tzinfo=UTC))
    next_runs = service.tick(now=datetime(2026, 5, 9, 12, 41, tzinfo=UTC))

    assert completed is not None
    assert completed.status == "succeeded"
    assert completed.confirmed_at == datetime(2026, 5, 9, 10, 40, tzinfo=UTC)
    assert completed.result["manual_completion"] is True
    assert deliveries_after_completion == []
    assert before_next_interval == []
    assert len(next_runs) == 1
    assert next_runs[0].scheduled_for == datetime(2026, 5, 9, 12, 40, tzinfo=UTC)


def test_complete_task_confirms_delayed_primary_run(tmp_path) -> None:
    shanghai = get_tzinfo("Asia/Shanghai")
    service = XushiService(
        Settings(
            database_path=tmp_path / "xushi.db",
            api_token="test-token",
            quiet_policy=QuietPolicy(
                enabled=True,
                timezone="Asia/Shanghai",
                windows=[QuietWindow(start="22:30", end="08:00")],
            ),
        )
    )
    task = service.create_task(
        TaskCreate(
            title="喝水",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 23, 0, tzinfo=shanghai),
                timezone="Asia/Shanghai",
            ),
            action={"type": "reminder", "payload": {"message": "喝水"}},
        )
    )
    run = service.trigger_task(task.id, now=datetime(2026, 5, 9, 23, 0, tzinfo=shanghai))

    completed = service.complete_task(
        task.id,
        now=datetime(2026, 5, 9, 23, 10, tzinfo=shanghai),
    )
    service.tick(now=datetime(2026, 5, 10, 8, 0, tzinfo=shanghai))

    updated = service.get_run(run.id)
    assert completed is not None
    assert completed.id == run.id
    assert completed.result["completion_source"] == "task_complete"
    assert updated is not None
    assert updated.status == "succeeded"
    assert service.list_deliveries()[0].status == "cancelled"
    assert service.list_notifications() == []


def test_completion_anchor_requires_confirmation_policy(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))

    with pytest.raises(InvalidTaskConfigurationError, match="requires confirmation"):
        service.create_task(
            TaskCreate(
                title="喝水",
                schedule=Schedule(
                    kind="recurring",
                    run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                    rrule="FREQ=HOURLY",
                    timezone="UTC",
                    anchor="completion",
                ),
                action={"type": "reminder", "payload": {"message": "喝水"}},
            )
        )


def test_update_to_completion_anchor_rejects_terminal_run_without_anchor(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    task = service.create_task(
        TaskCreate(
            title="喝水",
            schedule=Schedule(
                kind="recurring",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                rrule="FREQ=HOURLY",
                timezone="UTC",
                anchor="calendar",
            ),
            action={"type": "reminder", "payload": {"message": "喝水"}},
        )
    )
    first_run = service.tick(now=datetime(2026, 5, 9, 12, 1, tzinfo=UTC))[0]

    with pytest.raises(InvalidTaskConfigurationError, match="confirming the latest"):
        service.update_task(
            task.id,
            TaskPatch(
                schedule=Schedule(
                    kind="recurring",
                    run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                    rrule="FREQ=HOURLY",
                    timezone="UTC",
                    anchor="completion",
                ),
                follow_up_policy=FollowUpPolicy(requires_confirmation=True),
            ),
        )

    stored_task = service.get_task(task.id)
    assert first_run.status == "succeeded"
    assert first_run.confirmed_at is None
    assert stored_task is not None
    assert stored_task.schedule.anchor == "calendar"


def test_update_to_completion_anchor_allows_active_unconfirmed_run(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    task = service.create_task(
        TaskCreate(
            title="喝水",
            schedule=Schedule(
                kind="recurring",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                rrule="FREQ=HOURLY",
                timezone="UTC",
                anchor="calendar",
            ),
            action={"type": "reminder", "payload": {"message": "喝水"}},
            follow_up_policy=FollowUpPolicy(requires_confirmation=True),
        )
    )
    first_run = service.tick(now=datetime(2026, 5, 9, 12, 1, tzinfo=UTC))[0]

    updated = service.update_task(
        task.id,
        TaskPatch(
            schedule=Schedule(
                kind="recurring",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                rrule="FREQ=HOURLY",
                timezone="UTC",
                anchor="completion",
            ),
        ),
    )
    pending = service.tick(now=datetime(2026, 5, 9, 13, 1, tzinfo=UTC))
    service.confirm_run(first_run.id, now=datetime(2026, 5, 9, 12, 10, tzinfo=UTC))
    next_runs = service.tick(now=datetime(2026, 5, 9, 13, 11, tzinfo=UTC))

    assert updated is not None
    assert updated.schedule.anchor == "completion"
    assert first_run.status == "pending_confirmation"
    assert pending == []
    assert len(next_runs) == 1
    assert next_runs[0].scheduled_for == datetime(2026, 5, 9, 13, 10, tzinfo=UTC)


def test_tick_records_runtime_metrics(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    service.create_task(
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

    created = service.tick(now=datetime(2026, 5, 9, 12, 1, tzinfo=UTC))

    metrics = service.metrics_snapshot()
    latest_tick = metrics["recent_ticks"][-1]
    assert len(created) == 1
    assert metrics["counters"]["runs_created_total"] == 1
    assert metrics["counters"]["deliveries_succeeded_total"] == 1
    assert latest_tick["created_runs"] == 1
    assert latest_tick["processed_deliveries"] == 0
    assert latest_tick["created_follow_ups"] == 0
    assert latest_tick["duration_ms"] >= 0


def test_auto_retry_failed_deliveries_respects_attempt_limit(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OPENCLAW_HOOKS_TOKEN", raising=False)
    executor = Executor(
        id="openclaw",
        kind="openclaw",
        name="OpenClaw",
        config={
            "mode": "hooks_agent",
            "webhook_url": "http://127.0.0.1:18789/hooks/agent",
            "token_env": "OPENCLAW_HOOKS_TOKEN",
        },
    )
    service = XushiService(
        Settings(
            database_path=tmp_path / "xushi.db",
            api_token="test-token",
            executors=(executor,),
            auto_retry_failed_deliveries=True,
            auto_retry_max_attempts=1,
        )
    )
    task = service.create_task(
        TaskCreate(
            title="喝水",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                timezone="UTC",
            ),
            action={
                "type": "reminder",
                "executor_id": "openclaw",
                "payload": {"message": "喝水"},
            },
        )
    )
    service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))

    service.tick(now=datetime(2026, 5, 9, 12, 1, tzinfo=UTC))
    service.tick(now=datetime(2026, 5, 9, 12, 2, tzinfo=UTC))

    deliveries = service.list_deliveries()
    retry_deliveries = [delivery for delivery in deliveries if delivery.result.get("retry_of")]
    assert len(deliveries) == 2
    assert len(retry_deliveries) == 1
    assert retry_deliveries[0].result["auto_retry_attempts"] == 1
