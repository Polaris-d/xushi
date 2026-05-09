"""agent 平台载荷适配工具函数。"""

from __future__ import annotations

from typing import Any

DEFAULT_OPENCLAW_HOOKS_AGENT_URL = "http://127.0.0.1:18789/hooks/agent"
DEFAULT_OPENCLAW_TOKEN_ENVS = ("OPENCLAW_HOOKS_TOKEN", "OPENCLAW_WEBHOOK_TOKEN")


def build_openclaw_hooks_agent_body(
    payload: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """将序时 action payload 转换为 OpenClaw `/hooks/agent` 请求体。"""
    message = _openclaw_agent_message(payload)
    timeout_seconds = int(config.get("agent_timeout_seconds", config.get("timeout_seconds", 120)))
    body: dict[str, Any] = {
        "message": message,
        "name": str(config.get("name") or "xushi"),
        "wakeMode": str(config.get("wake_mode") or config.get("wakeMode") or "now"),
        "deliver": bool(config.get("deliver", True)),
        "channel": str(config.get("channel") or "last"),
        "timeoutSeconds": timeout_seconds,
    }
    optional_fields = {
        "to": config.get("to"),
        "agentId": config.get("agent_id", config.get("agentId")),
        "sessionKey": config.get("session_key", config.get("sessionKey")),
        "model": config.get("model"),
        "thinking": config.get("thinking"),
        "fallbacks": config.get("fallbacks"),
    }
    for key, value in optional_fields.items():
        if value is not None:
            body[key] = value
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


def parse_bool(value: str) -> bool:
    """解析常见环境变量布尔值。"""
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}
