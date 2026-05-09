"""agent 平台载荷适配测试。"""

from xushi.bridges import build_openclaw_hooks_agent_body


def test_openclaw_hooks_agent_body_maps_all_snake_case_config_fields() -> None:
    body = build_openclaw_hooks_agent_body(
        payload={"title": "饭后吃药", "message": "该吃药了"},
        config={
            "name": "Xushi Reminder",
            "agent_id": "reminder-agent",
            "session_key": "hook:xushi:run_1",
            "wake_mode": "next-heartbeat",
            "deliver": "false",
            "channel": "feishu",
            "to": "chat_123",
            "model": "openai/gpt-5.4-mini",
            "fallbacks": ["openai/gpt-5.4"],
            "thinking": "low",
            "timeout_seconds": 45,
        },
    )

    assert body["name"] == "Xushi Reminder"
    assert body["agentId"] == "reminder-agent"
    assert body["sessionKey"] == "hook:xushi:run_1"
    assert body["wakeMode"] == "next-heartbeat"
    assert body["deliver"] is False
    assert body["channel"] == "feishu"
    assert body["to"] == "chat_123"
    assert body["model"] == "openai/gpt-5.4-mini"
    assert body["fallbacks"] == ["openai/gpt-5.4"]
    assert body["thinking"] == "low"
    assert body["timeoutSeconds"] == 45


def test_openclaw_hooks_agent_body_accepts_camel_case_config_fields() -> None:
    body = build_openclaw_hooks_agent_body(
        payload={"prompt": "提醒我喝水"},
        config={
            "agentId": "hooks",
            "sessionKey": "hook:xushi:drink-water",
            "wakeMode": "now",
            "timeoutSeconds": 90,
            "deliver": True,
        },
    )

    assert body["message"] == "提醒我喝水"
    assert body["agentId"] == "hooks"
    assert body["sessionKey"] == "hook:xushi:drink-water"
    assert body["wakeMode"] == "now"
    assert body["timeoutSeconds"] == 90
    assert body["deliver"] is True


def test_openclaw_hooks_agent_body_does_not_default_channel_to_last() -> None:
    body = build_openclaw_hooks_agent_body(
        payload={"message": "提醒"},
        config={},
    )

    assert "channel" not in body
