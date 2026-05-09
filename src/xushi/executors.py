"""执行器注册与调用。"""

from __future__ import annotations

import json
import subprocess
from typing import Any
from urllib import error, request

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
        if executor.kind == "command":
            return self._execute_command(action, executor)
        if executor.kind == "webhook":
            return self._execute_webhook(action, executor)
        if executor.kind in {"openclaw", "hermes"}:
            return self._execute_agent(action, executor)
        return {"delivered": False, "error": f"unsupported executor kind: {executor.kind}"}

    def _execute_command(self, action: Action, executor: Executor) -> dict[str, Any]:
        command = executor.config.get("command")
        if not command:
            return {"delivered": False, "error": "command executor missing command"}
        completed = subprocess.run(
            command,
            input=str(action.payload),
            capture_output=True,
            check=False,
            shell=True,
            text=True,
            timeout=int(executor.config.get("timeout_seconds", 30)),
        )
        return {
            "delivered": completed.returncode == 0,
            "executor": executor.id,
            "kind": executor.kind,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    def _execute_agent(self, action: Action, executor: Executor) -> dict[str, Any]:
        if executor.config.get("webhook_url"):
            return self._execute_webhook(action, executor)
        if executor.config.get("command"):
            return self._execute_command(action, executor)
        return {
            "delivered": False,
            "executor": executor.id,
            "kind": executor.kind,
            "error": f"{executor.kind} executor missing command or webhook_url",
        }

    def _execute_webhook(self, action: Action, executor: Executor) -> dict[str, Any]:
        webhook_url = executor.config.get("webhook_url")
        if not webhook_url:
            return {
                "delivered": False,
                "executor": executor.id,
                "kind": executor.kind,
                "error": "webhook executor missing webhook_url",
            }

        body = json.dumps(
            {
                "executor": {
                    "id": executor.id,
                    "kind": executor.kind,
                    "name": executor.name,
                },
                "payload": action.payload,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {
            "content-type": "application/json",
            "user-agent": "xushi/0.1.0",
        }
        token = executor.config.get("token")
        if token:
            headers["authorization"] = f"Bearer {token}"
        req = request.Request(str(webhook_url), data=body, headers=headers, method="POST")
        try:
            timeout_seconds = int(executor.config.get("timeout_seconds", 30))
            with request.urlopen(req, timeout=timeout_seconds) as resp:
                response_body = resp.read().decode("utf-8")
                status_code = resp.status
        except error.HTTPError as exc:
            response_body = exc.read().decode("utf-8")
            return {
                "delivered": False,
                "executor": executor.id,
                "kind": executor.kind,
                "status_code": exc.code,
                "response_text": response_body,
                "error": str(exc),
            }
        except OSError as exc:
            return {
                "delivered": False,
                "executor": executor.id,
                "kind": executor.kind,
                "error": str(exc),
            }

        response_json = None
        try:
            response_json = json.loads(response_body) if response_body else None
        except json.JSONDecodeError:
            response_json = None
        return {
            "delivered": 200 <= status_code < 300,
            "executor": executor.id,
            "kind": executor.kind,
            "status_code": status_code,
            "response_text": response_body,
            "response_json": response_json,
        }
