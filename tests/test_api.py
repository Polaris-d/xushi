"""HTTP API 测试。"""

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from xushi.api import create_app
from xushi.config import Settings
from xushi.models import Executor


def _write_config(
    path,
    *,
    api_token: str,
    database_path,
    executors: list[dict],
    quiet_policy: dict | None = None,
) -> None:
    payload = {
        "api_token": api_token,
        "database_path": str(database_path),
        "host": "127.0.0.1",
        "port": 18766,
        "scheduler_interval_seconds": 30,
        "quiet_policy": quiet_policy or {"enabled": False},
        "executors": executors,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_create_and_fetch_task(tmp_path) -> None:
    settings = Settings(
        database_path=tmp_path / "xushi.db",
        api_token="test-token",
        host="127.0.0.1",
        port=8765,
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer test-token"},
        json={
            "title": "饭后吃药",
            "schedule": {
                "kind": "one_shot",
                "run_at": datetime(2026, 5, 9, 12, 0, tzinfo=UTC).isoformat(),
                "timezone": "UTC",
            },
            "action": {"type": "reminder", "payload": {"message": "饭后吃药"}},
            "follow_up_policy": {
                "requires_confirmation": True,
                "grace_period": "PT10M",
                "interval": "PT5M",
                "max_attempts": 3,
            },
        },
    )

    assert response.status_code == 201
    task_id = response.json()["data"]["id"]

    fetch_response = client.get(
        f"/api/v1/tasks/{task_id}",
        headers={"Authorization": "Bearer test-token"},
    )

    assert fetch_response.status_code == 200
    assert fetch_response.json()["data"]["title"] == "饭后吃药"


def test_api_rejects_missing_token(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "xushi.db", api_token="test-token")
    client = TestClient(create_app(settings))

    response = client.get("/api/v1/tasks")

    assert response.status_code == 401
    assert response.json() == {
        "status": 401,
        "code": 401,
        "message": "invalid token",
        "data": None,
        "errors": [{"detail": "invalid token"}],
    }


def test_api_returns_unified_not_found_error(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "xushi.db", api_token="test-token")
    client = TestClient(create_app(settings))

    response = client.get(
        "/api/v1/tasks/missing",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "status": 404,
        "code": 404,
        "message": "task not found",
        "data": None,
        "errors": [{"detail": "task not found"}],
    }


def test_capabilities_endpoint_is_public_and_agent_readable(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "xushi.db", api_token="test-token")
    client = TestClient(create_app(settings))

    response = client.get("/api/v1/capabilities")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["entrypoints"]["http"]["openapi"] == "GET /openapi.json"
    assert payload["entrypoints"]["cli"]["capabilities"] == "xushi capabilities"
    confirm_latest = next(
        item for item in payload["capabilities"] if item["id"] == "confirm_latest_run"
    )
    assert confirm_latest["http"]["path"] == "/api/v1/tasks/{task_id}/runs/confirm-latest"
    assert confirm_latest["cli"]["command"] == "xushi confirm-latest <task_id>"
    assert confirm_latest["openclaw_plugin"]["tool"] == "xushi_confirm_latest_run"
    complete_task = next(item for item in payload["capabilities"] if item["id"] == "complete_task")
    assert complete_task["http"]["path"] == "/api/v1/tasks/{task_id}/complete"
    assert complete_task["cli"]["command"] == "xushi complete <task_id>"
    assert complete_task["openclaw_plugin"]["tool"] == "xushi_complete_task"


def test_create_task_rejects_naive_datetime(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "xushi.db", api_token="test-token")
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer test-token"},
        json={
            "title": "饭后吃药",
            "schedule": {
                "kind": "one_shot",
                "run_at": "2026-05-09T12:00:00",
                "timezone": "Asia/Shanghai",
            },
            "action": {"type": "reminder", "payload": {"message": "饭后吃药"}},
        },
    )

    assert response.status_code == 422
    assert "timezone-aware" in response.text


def test_create_task_rejects_completion_anchor_without_confirmation(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "xushi.db", api_token="test-token")
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer test-token"},
        json={
            "title": "喝水",
            "schedule": {
                "kind": "recurring",
                "run_at": datetime(2026, 5, 9, 12, 0, tzinfo=UTC).isoformat(),
                "rrule": "FREQ=HOURLY",
                "timezone": "UTC",
                "anchor": "completion",
            },
            "action": {"type": "reminder", "payload": {"message": "喝水"}},
        },
    )

    assert response.status_code == 400
    assert response.json()["message"] == "completion anchor requires confirmation"


def test_update_task_rejects_completion_anchor_without_completion_anchor(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "xushi.db", api_token="test-token")
    client = TestClient(create_app(settings))
    create_response = client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer test-token"},
        json={
            "title": "喝水",
            "schedule": {
                "kind": "recurring",
                "run_at": datetime(2026, 5, 9, 12, 0, tzinfo=UTC).isoformat(),
                "rrule": "FREQ=HOURLY",
                "timezone": "UTC",
                "anchor": "calendar",
            },
            "action": {"type": "reminder", "payload": {"message": "喝水"}},
        },
    )
    task_id = create_response.json()["data"]["id"]
    client.post(
        f"/api/v1/tasks/{task_id}/runs",
        headers={"Authorization": "Bearer test-token"},
    )

    response = client.patch(
        f"/api/v1/tasks/{task_id}",
        headers={"Authorization": "Bearer test-token"},
        json={
            "schedule": {
                "kind": "recurring",
                "run_at": datetime(2026, 5, 9, 12, 0, tzinfo=UTC).isoformat(),
                "rrule": "FREQ=HOURLY",
                "timezone": "UTC",
                "anchor": "completion",
            },
            "follow_up_policy": {"requires_confirmation": True},
        },
    )

    assert response.status_code == 400
    assert response.json()["message"] == (
        "switching to completion anchor requires confirming the latest primary run"
    )


def test_create_task_rejects_idempotency_key_conflict(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "xushi.db", api_token="test-token")
    client = TestClient(create_app(settings))
    base_payload = {
        "title": "生成日报",
        "schedule": {
            "kind": "one_shot",
            "run_at": datetime(2026, 5, 9, 12, 0, tzinfo=UTC).isoformat(),
            "timezone": "UTC",
        },
        "action": {"type": "reminder", "payload": {"message": "生成日报"}},
        "idempotency_key": "agent-retry-conflict",
    }
    first_response = client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer test-token"},
        json=base_payload,
    )
    conflict_payload = {
        **base_payload,
        "title": "生成晚报",
        "schedule": {
            "kind": "one_shot",
            "run_at": datetime(2026, 5, 9, 18, 0, tzinfo=UTC).isoformat(),
            "timezone": "UTC",
        },
        "action": {"type": "reminder", "payload": {"message": "生成晚报"}},
    }

    conflict_response = client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer test-token"},
        json=conflict_payload,
    )

    assert first_response.status_code == 201
    assert conflict_response.status_code == 409
    assert conflict_response.json()["message"] == "idempotency key conflict"


def test_confirm_run_endpoint(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "xushi.db", api_token="test-token")
    client = TestClient(create_app(settings))
    create_response = client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer test-token"},
        json={
            "title": "吃药",
            "schedule": {
                "kind": "one_shot",
                "run_at": datetime(2026, 5, 9, 12, 0, tzinfo=UTC).isoformat(),
                "timezone": "UTC",
            },
            "action": {"type": "reminder", "payload": {"message": "吃药"}},
            "follow_up_policy": {"requires_confirmation": True},
        },
    )
    task_id = create_response.json()["data"]["id"]
    run_response = client.post(
        f"/api/v1/tasks/{task_id}/runs",
        headers={"Authorization": "Bearer test-token"},
    )
    run_id = run_response.json()["data"]["id"]

    confirm_response = client.post(
        f"/api/v1/runs/{run_id}/confirm",
        headers={"Authorization": "Bearer test-token"},
    )

    assert confirm_response.status_code == 200
    assert confirm_response.json()["data"]["status"] == "succeeded"


def test_confirm_latest_run_endpoint_and_run_filters(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "xushi.db", api_token="test-token")
    client = TestClient(create_app(settings))
    create_response = client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer test-token"},
        json={
            "title": "喝水",
            "schedule": {
                "kind": "one_shot",
                "run_at": datetime(2026, 5, 9, 12, 0, tzinfo=UTC).isoformat(),
                "timezone": "UTC",
            },
            "action": {"type": "reminder", "payload": {"message": "喝水"}},
            "follow_up_policy": {"requires_confirmation": True},
        },
    )
    task_id = create_response.json()["data"]["id"]
    first_run = client.post(
        f"/api/v1/tasks/{task_id}/runs",
        headers={"Authorization": "Bearer test-token"},
    ).json()["data"]
    second_run = client.post(
        f"/api/v1/tasks/{task_id}/runs",
        headers={"Authorization": "Bearer test-token"},
    ).json()["data"]

    confirm_response = client.post(
        f"/api/v1/tasks/{task_id}/runs/confirm-latest",
        headers={"Authorization": "Bearer test-token"},
    )
    pending_response = client.get(
        f"/api/v1/runs?task_id={task_id}&status=pending_confirmation",
        headers={"Authorization": "Bearer test-token"},
    )
    active_response = client.get(
        f"/api/v1/runs?task_id={task_id}&active_only=true",
        headers={"Authorization": "Bearer test-token"},
    )
    limited_response = client.get(
        "/api/v1/runs?limit=1",
        headers={"Authorization": "Bearer test-token"},
    )

    assert confirm_response.status_code == 200
    assert confirm_response.json()["data"]["id"] == second_run["id"]
    assert confirm_response.json()["data"]["status"] == "succeeded"
    assert [item["id"] for item in pending_response.json()["data"]] == [first_run["id"]]
    assert [item["id"] for item in active_response.json()["data"]] == [first_run["id"]]
    assert len(limited_response.json()["data"]) == 1


def test_complete_task_endpoint_creates_manual_completion_anchor(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "xushi.db", api_token="test-token")
    client = TestClient(create_app(settings))
    create_response = client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer test-token"},
        json={
            "title": "喝水",
            "schedule": {
                "kind": "recurring",
                "run_at": datetime(2026, 5, 9, 12, 0, tzinfo=UTC).isoformat(),
                "rrule": "FREQ=HOURLY;INTERVAL=2",
                "timezone": "UTC",
                "anchor": "completion",
            },
            "action": {"type": "reminder", "payload": {"message": "喝水"}},
            "follow_up_policy": {"requires_confirmation": True},
        },
    )
    task_id = create_response.json()["data"]["id"]

    complete_response = client.post(
        f"/api/v1/tasks/{task_id}/complete",
        headers={"Authorization": "Bearer test-token"},
    )

    assert complete_response.status_code == 200
    data = complete_response.json()["data"]
    assert data["status"] == "succeeded"
    assert data["confirmed_at"] is not None
    assert data["result"]["manual_completion"] is True


def test_run_list_uses_safe_default_limit(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "xushi.db", api_token="test-token")
    client = TestClient(create_app(settings))
    create_response = client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer test-token"},
        json={
            "title": "喝水",
            "schedule": {
                "kind": "one_shot",
                "run_at": datetime(2026, 5, 9, 12, 0, tzinfo=UTC).isoformat(),
                "timezone": "UTC",
            },
            "action": {"type": "reminder", "payload": {"message": "喝水"}},
        },
    )
    task_id = create_response.json()["data"]["id"]
    for _ in range(105):
        client.post(
            f"/api/v1/tasks/{task_id}/runs",
            headers={"Authorization": "Bearer test-token"},
        )

    default_response = client.get(
        "/api/v1/runs",
        headers={"Authorization": "Bearer test-token"},
    )
    expanded_response = client.get(
        "/api/v1/runs?limit=105",
        headers={"Authorization": "Bearer test-token"},
    )

    assert len(default_response.json()["data"]) == 100
    assert len(expanded_response.json()["data"]) == 105


def test_metrics_endpoint_reports_counters_and_recent_ticks(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "xushi.db", api_token="test-token")
    client = TestClient(create_app(settings))
    create_response = client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer test-token"},
        json={
            "title": "喝水",
            "schedule": {
                "kind": "one_shot",
                "run_at": datetime(2026, 5, 9, 12, 0, tzinfo=UTC).isoformat(),
                "timezone": "UTC",
            },
            "action": {"type": "reminder", "payload": {"message": "喝水"}},
        },
    )
    task_id = create_response.json()["data"]["id"]

    client.post(
        f"/api/v1/tasks/{task_id}/runs",
        headers={"Authorization": "Bearer test-token"},
    )
    response = client.get(
        "/api/v1/metrics",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["counters"]["runs_created_total"] == 1
    assert data["counters"]["deliveries_succeeded_total"] == 1
    assert data["recent_ticks"] == []


def test_list_notifications_endpoint(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "xushi.db", api_token="test-token")
    client = TestClient(create_app(settings))

    response = client.get(
        "/api/v1/notifications",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_list_deliveries_endpoint(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "xushi.db", api_token="test-token")
    client = TestClient(create_app(settings))

    response = client.get(
        "/api/v1/deliveries",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_retry_deliveries_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OPENCLAW_HOOKS_TOKEN", raising=False)
    settings = Settings(
        database_path=tmp_path / "xushi.db",
        api_token="test-token",
        executors=(
            Executor(
                id="openclaw",
                kind="openclaw",
                name="OpenClaw",
                config={
                    "mode": "hooks_agent",
                    "webhook_url": "http://127.0.0.1:18789/hooks/agent",
                    "token_env": "OPENCLAW_HOOKS_TOKEN",
                },
            ),
        ),
    )
    client = TestClient(create_app(settings))
    create_response = client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer test-token"},
        json={
            "title": "喝水",
            "schedule": {
                "kind": "one_shot",
                "run_at": datetime(2026, 5, 9, 12, 0, tzinfo=UTC).isoformat(),
                "timezone": "UTC",
            },
            "action": {
                "type": "reminder",
                "executor_id": "openclaw",
                "payload": {"message": "喝水"},
            },
        },
    )
    task_id = create_response.json()["data"]["id"]
    run_response = client.post(
        f"/api/v1/tasks/{task_id}/runs",
        headers={"Authorization": "Bearer test-token"},
    )
    failed_delivery_id = run_response.json()["data"]["result"]["delivery_id"]

    response = client.post(
        "/api/v1/deliveries/retry",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    retried = response.json()["data"]
    assert len(retried) == 1
    assert retried[0]["status"] == "failed"
    assert retried[0]["result"]["retry_of"] == failed_delivery_id


def test_config_reload_updates_runtime_executors_and_quiet_policy(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    database_path = tmp_path / "xushi.db"
    old_executors = [
        {
            "id": "old-openclaw",
            "kind": "openclaw",
            "name": "Old OpenClaw",
            "config": {
                "mode": "hooks_agent",
                "webhook_url": "http://127.0.0.1:18789/hooks/agent",
            },
        }
    ]
    new_executors = [
        {
            "id": "new-openclaw",
            "kind": "openclaw",
            "name": "New OpenClaw",
            "config": {
                "mode": "hooks_agent",
                "webhook_url": "http://127.0.0.1:18790/hooks/agent",
            },
        }
    ]
    _write_config(
        config_path,
        api_token="old-token",
        database_path=database_path,
        executors=old_executors,
    )
    monkeypatch.setenv("XUSHI_CONFIG_PATH", str(config_path))
    client = TestClient(create_app())

    before_reload = client.get(
        "/api/v1/executors",
        headers={"Authorization": "Bearer old-token"},
    )

    _write_config(
        config_path,
        api_token="new-token",
        database_path=tmp_path / "changed.db",
        executors=new_executors,
        quiet_policy={
            "enabled": True,
            "timezone": "Asia/Shanghai",
            "windows": [{"start": "00:00", "end": "24:00", "days": "everyday"}],
            "behavior": "delay",
        },
    )
    reload_response = client.post(
        "/api/v1/config/reload",
        headers={"Authorization": "Bearer old-token"},
    )
    after_reload = client.get(
        "/api/v1/executors",
        headers={"Authorization": "Bearer old-token"},
    )
    new_token_response = client.get(
        "/api/v1/executors",
        headers={"Authorization": "Bearer new-token"},
    )
    create_response = client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer old-token"},
        json={
            "title": "夜间提醒",
            "schedule": {
                "kind": "one_shot",
                "run_at": "2026-05-11T23:00:00+08:00",
                "timezone": "Asia/Shanghai",
            },
            "action": {"type": "reminder", "payload": {"message": "夜间提醒"}},
        },
    )
    task_id = create_response.json()["data"]["id"]
    run_response = client.post(
        f"/api/v1/tasks/{task_id}/runs",
        headers={"Authorization": "Bearer old-token"},
    )
    deliveries_response = client.get(
        "/api/v1/deliveries",
        headers={"Authorization": "Bearer old-token"},
    )

    assert before_reload.json()["data"][0]["id"] == "old-openclaw"
    assert reload_response.status_code == 200
    assert reload_response.json()["data"] == {
        "reloaded": ["executors", "quiet_policy", "auto_retry_policy"],
        "restart_required": [
            "api_token",
            "database_path",
            "host",
            "port",
            "scheduler_interval_seconds",
            "sqlite_journal_mode",
            "sqlite_synchronous",
        ],
        "executors": 1,
        "enabled_executors": 1,
        "quiet_policy_enabled": True,
        "auto_retry_failed_deliveries": False,
        "auto_retry_max_attempts": 1,
    }
    assert after_reload.json()["data"][0]["id"] == "new-openclaw"
    assert new_token_response.status_code == 401
    assert run_response.json()["data"]["status"] == "pending_delivery"
    assert deliveries_response.json()["data"][0]["status"] == "delayed"


def test_config_reload_keeps_previous_runtime_when_config_is_invalid(
    tmp_path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.json"
    old_executors = [
        {
            "id": "old-openclaw",
            "kind": "openclaw",
            "name": "Old OpenClaw",
            "config": {
                "mode": "hooks_agent",
                "webhook_url": "http://127.0.0.1:18789/hooks/agent",
            },
        }
    ]
    _write_config(
        config_path,
        api_token="old-token",
        database_path=tmp_path / "xushi.db",
        executors=old_executors,
    )
    monkeypatch.setenv("XUSHI_CONFIG_PATH", str(config_path))
    client = TestClient(create_app())

    _write_config(
        config_path,
        api_token="old-token",
        database_path=tmp_path / "xushi.db",
        executors=[
            {
                "id": "bad-executor",
                "kind": "command",
                "name": "Bad Executor",
                "config": {},
            }
        ],
    )

    reload_response = client.post(
        "/api/v1/config/reload",
        headers={"Authorization": "Bearer old-token"},
    )
    executors_response = client.get(
        "/api/v1/executors",
        headers={"Authorization": "Bearer old-token"},
    )

    assert reload_response.status_code == 400
    assert reload_response.json()["message"] == "config reload failed"
    assert executors_response.json()["data"][0]["id"] == "old-openclaw"


def test_executor_api_is_read_only_and_uses_config_file(tmp_path) -> None:
    settings = Settings(
        database_path=tmp_path / "xushi.db",
        api_token="test-token",
        executors=(
            Executor(
                id="openclaw",
                kind="openclaw",
                name="OpenClaw",
                config={
                    "mode": "hooks_agent",
                    "webhook_url": "http://127.0.0.1:18789/hooks/agent",
                },
            ),
        ),
    )
    client = TestClient(create_app(settings))

    list_response = client.get(
        "/api/v1/executors",
        headers={"Authorization": "Bearer test-token"},
    )
    post_response = client.post(
        "/api/v1/executors",
        headers={"Authorization": "Bearer test-token"},
        json={
            "id": "custom",
            "kind": "webhook",
            "name": "Custom",
            "config": {},
        },
    )

    assert list_response.status_code == 200
    assert list_response.json()["data"][0]["id"] == "openclaw"
    assert post_response.status_code == 405


def test_run_callback_endpoint_updates_status(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "xushi.db", api_token="test-token")
    client = TestClient(create_app(settings))
    create_response = client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer test-token"},
        json={
            "title": "长任务",
            "schedule": {
                "kind": "one_shot",
                "run_at": datetime(2026, 5, 9, 12, 0, tzinfo=UTC).isoformat(),
                "timezone": "UTC",
            },
            "action": {"type": "reminder", "payload": {"message": "长任务"}},
            "follow_up_policy": {"requires_confirmation": True},
        },
    )
    task_id = create_response.json()["data"]["id"]
    run_response = client.post(
        f"/api/v1/tasks/{task_id}/runs",
        headers={"Authorization": "Bearer test-token"},
    )
    run_id = run_response.json()["data"]["id"]

    callback_response = client.post(
        f"/api/v1/runs/{run_id}/callback",
        headers={"Authorization": "Bearer test-token"},
        json={"status": "succeeded", "result": {"agent_run_id": "remote_1"}},
    )

    assert callback_response.status_code == 200
    assert callback_response.json()["data"]["status"] == "succeeded"
    assert callback_response.json()["data"]["result"]["agent_run_id"] == "remote_1"
