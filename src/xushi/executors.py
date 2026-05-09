"""执行器注册与调用。"""

from __future__ import annotations

import json
import os
import ssl
from typing import Any
from urllib import error, request

from xushi.bridges import (
    DEFAULT_OPENCLAW_HOOKS_AGENT_URL,
    DEFAULT_OPENCLAW_TOKEN_ENVS,
    build_openclaw_hooks_agent_body,
    parse_bool,
)
from xushi.models import Action, Executor
from xushi.notifications import NotificationDispatcher, notification_payload


class ExecutorRegistry:
    """执行器调用入口。"""

    def __init__(self, notifications: NotificationDispatcher | None = None) -> None:
        self.notifications = notifications or NotificationDispatcher()

    def execute(self, action: Action, executor: Executor | None = None) -> dict[str, Any]:
        """执行任务动作并返回同步结果。"""
        if action.type == "reminder":
            if action.executor_id:
                if executor is None:
                    return {"delivered": False, "error": "executor not found"}
                return self._execute_executor(action, executor)
            title = action.payload.get("title") or action.payload.get("message") or "序时提醒"
            event = self.notifications.notify(
                title=str(title),
                message=str(action.payload.get("message") or action.payload),
                task_id=action.payload.get("task_id"),
                run_id=action.payload.get("run_id"),
                kind=str(action.payload.get("kind") or "reminder"),
            )
            return {
                "delivered": event.status in {"delivered", "fallback_logged"},
                "channel": event.channel,
                "payload": action.payload,
                **notification_payload(event),
            }
        if executor is None:
            return {"delivered": False, "error": "executor not found"}
        return self._execute_executor(action, executor)

    def _execute_executor(self, action: Action, executor: Executor) -> dict[str, Any]:
        """调用外部执行器。"""
        if executor.kind == "openclaw":
            return self._execute_openclaw(action, executor)
        if executor.kind == "webhook":
            return self._reserved_executor(executor)
        if executor.kind == "hermes":
            return self._reserved_executor(executor)
        return {"delivered": False, "error": f"unsupported executor kind: {executor.kind}"}

    def _execute_openclaw(self, action: Action, executor: Executor) -> dict[str, Any]:
        mode = str(executor.config.get("mode") or "hooks_agent")
        if mode == "hooks_agent":
            return self._execute_openclaw_hooks_agent(action, executor)
        return {
            "delivered": False,
            "executor": executor.id,
            "kind": executor.kind,
            "mode": mode,
            "error": f"unsupported openclaw executor mode: {mode}",
        }

    def _execute_openclaw_hooks_agent(self, action: Action, executor: Executor) -> dict[str, Any]:
        webhook_url = str(executor.config.get("webhook_url") or DEFAULT_OPENCLAW_HOOKS_AGENT_URL)
        token = self._resolve_token(executor, default_envs=DEFAULT_OPENCLAW_TOKEN_ENVS)
        if not token:
            return {
                "delivered": False,
                "executor": executor.id,
                "kind": executor.kind,
                "mode": "hooks_agent",
                "error": "openclaw hooks_agent executor missing token or token_env",
            }
        body = build_openclaw_hooks_agent_body(action.payload, executor.config)
        timeout_seconds = int(executor.config.get("request_timeout_seconds", 30))
        insecure_tls = parse_bool(str(executor.config.get("insecure_tls", "true")))
        result = self._post_json(
            url=webhook_url,
            body=body,
            token=token,
            timeout_seconds=timeout_seconds,
            insecure_tls=insecure_tls,
        )
        return {
            **result,
            "executor": executor.id,
            "kind": executor.kind,
            "mode": "hooks_agent",
        }

    def _reserved_executor(self, executor: Executor) -> dict[str, Any]:
        """返回预留执行器未实现状态。"""
        return {
            "delivered": False,
            "executor": executor.id,
            "kind": executor.kind,
            "error": f"{executor.kind} executor reserved but not implemented",
        }

    def _resolve_token(self, executor: Executor, default_envs: tuple[str, ...] = ()) -> str | None:
        """从配置或环境变量解析 token。"""
        token = executor.config.get("token")
        if token:
            return str(token)
        token_env = executor.config.get("token_env")
        if token_env:
            return os.environ.get(str(token_env))
        for env_name in default_envs:
            token = os.environ.get(env_name)
            if token:
                return token
        return None

    def _post_json(
        self,
        url: str,
        body: dict[str, Any],
        token: object | None = None,
        timeout_seconds: int = 30,
        insecure_tls: bool = False,
    ) -> dict[str, Any]:
        """发送 JSON POST 请求。"""
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "content-type": "application/json",
            "user-agent": "xushi/0.1.0",
        }
        if token:
            headers["authorization"] = f"Bearer {token}"
        req = request.Request(url, data=data, headers=headers, method="POST")
        context = ssl._create_unverified_context() if insecure_tls else None
        try:
            with request.urlopen(req, timeout=timeout_seconds, context=context) as resp:
                response_body = resp.read().decode("utf-8")
                status_code = resp.status
        except error.HTTPError as exc:
            response_body = exc.read().decode("utf-8")
            return {
                "delivered": False,
                "status_code": exc.code,
                "response_text": response_body,
                "error": str(exc),
            }
        except OSError as exc:
            return {
                "delivered": False,
                "error": str(exc),
            }

        response_json = None
        try:
            response_json = json.loads(response_body) if response_body else None
        except json.JSONDecodeError:
            response_json = None
        return {
            "delivered": 200 <= status_code < 300,
            "status_code": status_code,
            "response_text": response_body,
            "response_json": response_json,
        }
