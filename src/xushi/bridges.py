"""agent 平台载荷适配工具函数。"""

from __future__ import annotations

from typing import Any

DEFAULT_OPENCLAW_HOOKS_AGENT_URL = "http://127.0.0.1:18789/hooks/agent"
DEFAULT_OPENCLAW_TOKEN_ENVS = ("OPENCLAW_HOOKS_TOKEN", "OPENCLAW_WEBHOOK_TOKEN")
DEFAULT_HERMES_TOKEN_ENVS = ("HERMES_API_TOKEN", "HERMES_TOKEN")


def build_openclaw_hooks_agent_body(
    payload: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """将序时 action payload 转换为 OpenClaw `/hooks/agent` 请求体。"""
    message = _openclaw_agent_message(payload)
    timeout_seconds = _config_int(
        config,
        "agent_timeout_seconds",
        "timeout_seconds",
        "timeoutSeconds",
        default=120,
    )
    body: dict[str, Any] = {
        "message": message,
        "name": str(_config_value(config, "name", default="xushi")),
        "wakeMode": str(_config_value(config, "wake_mode", "wakeMode", default="now")),
        "deliver": _config_bool(config, "deliver", default=True),
        "timeoutSeconds": timeout_seconds,
    }
    optional_fields = {
        "channel": _config_value(config, "channel"),
        "to": _config_value(config, "to"),
        "agentId": _config_value(config, "agent_id", "agentId"),
        "sessionKey": _config_value(config, "session_key", "sessionKey"),
        "model": _config_value(config, "model"),
        "thinking": _config_value(config, "thinking"),
        "fallbacks": _config_value(config, "fallbacks"),
    }
    for key, value in optional_fields.items():
        if value is not None:
            body[key] = value
    return body


def build_hermes_agent_body(
    payload: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """将序时 action payload 转换为 Hermes agent webhook 请求体。"""
    prompt = _hermes_agent_prompt(payload)
    message_field = str(_config_value(config, "message_field", default="prompt"))
    body: dict[str, Any] = {
        message_field: prompt,
        "source": str(_config_value(config, "source", default="xushi")),
        "metadata": _hermes_metadata(payload),
    }
    optional_fields = {
        "agent_id": _config_value(config, "agent_id", "agentId"),
        "conversation_id": _config_value(
            config,
            "conversation_id",
            "conversationId",
            "session_key",
            "sessionKey",
        ),
        "channel": _config_value(config, "channel"),
        "to": _config_value(config, "to"),
        "model": _config_value(config, "model"),
        "thinking": _config_value(config, "thinking"),
        "deliver": _config_value(config, "deliver"),
    }
    for key, value in optional_fields.items():
        if value is not None:
            body[key] = value

    extra_body = _config_value(config, "body", "extra_body")
    if isinstance(extra_body, dict):
        body.update(extra_body)
    return body


def _openclaw_agent_message(payload: dict[str, Any]) -> str:
    """生成交给 OpenClaw agent 的自然语言提醒提示。"""
    if payload.get("prompt") and not payload.get("title") and not payload.get("message"):
        return str(payload["prompt"])
    kind = str(payload.get("kind") or "reminder")
    title = str(payload.get("title") or "序时提醒")
    message = str(payload.get("message") or "")
    task_id = payload.get("task_id")
    run_id = payload.get("run_id")

    if kind == "follow_up":
        parts = [
            "请把下面的序时跟进提醒转成简短、自然、适合发送给用户的中文提醒。",
            f"事项: {title}",
            "状态: 仍未确认完成",
        ]
    else:
        parts = [
            "请把下面的序时提醒转成简短、自然、适合发送给用户的中文提醒。",
            f"事项: {title}",
        ]
    if message:
        parts.append(f"内容: {message}")
    if task_id:
        parts.append(f"任务ID: {task_id}")
    if run_id:
        parts.append(f"运行ID: {run_id}")
    parts.append("请直接给用户一条可读提醒, 不要输出 JSON。")
    return "\n".join(parts)


def _hermes_agent_prompt(payload: dict[str, Any]) -> str:
    """生成交给 Hermes agent 的自然语言提醒提示。"""
    if payload.get("prompt") and not payload.get("title") and not payload.get("message"):
        return str(payload["prompt"])
    kind = str(payload.get("kind") or "reminder")
    title = str(payload.get("title") or "序时提醒")
    message = str(payload.get("message") or "")
    task_id = payload.get("task_id")
    run_id = payload.get("run_id")

    if kind == "follow_up":
        parts = [
            "请处理下面这条由序时触发的跟进提醒。",
            f"事项: {title}",
            "状态: 仍未确认完成",
        ]
    else:
        parts = [
            "请处理下面这条由序时触发的提醒。",
            f"事项: {title}",
        ]
    if message:
        parts.append(f"内容: {message}")
    if task_id:
        parts.append(f"任务ID: {task_id}")
    if run_id:
        parts.append(f"运行ID: {run_id}")
    parts.append("请直接给用户一条可读提醒, 不要输出 JSON。")
    return "\n".join(parts)


def _hermes_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """生成 Hermes 调用元数据。"""
    metadata: dict[str, Any] = {
        "origin": "xushi",
        "kind": str(payload.get("kind") or "reminder"),
    }
    for key in ("task_id", "run_id"):
        if payload.get(key):
            metadata[key] = payload[key]
    payload_metadata = payload.get("metadata")
    if isinstance(payload_metadata, dict):
        metadata.update(payload_metadata)
    return metadata


def _config_value(config: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """按别名顺序读取配置值。"""
    for key in keys:
        if key in config and config[key] is not None:
            return config[key]
    return default


def _config_bool(config: dict[str, Any], *keys: str, default: bool) -> bool:
    """按别名顺序读取布尔配置值。"""
    value = _config_value(config, *keys, default=default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return parse_bool(value)
    return bool(value)


def _config_int(config: dict[str, Any], *keys: str, default: int) -> int:
    """按别名顺序读取整数配置值。"""
    value = _config_value(config, *keys, default=default)
    return int(value)


def parse_bool(value: str) -> bool:
    """解析常见环境变量布尔值。"""
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}
