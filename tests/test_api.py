"""HTTP API 测试。"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from xushi.api import create_app
from xushi.config import Settings
from xushi.models import Executor


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


def test_list_notifications_endpoint(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "xushi.db", api_token="test-token")
    client = TestClient(create_app(settings))

    response = client.get(
        "/api/v1/notifications",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == []


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
