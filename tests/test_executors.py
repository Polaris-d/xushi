"""执行器真实调用测试。"""

from __future__ import annotations

import json
import ssl
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar
from urllib import request

from xushi.executors import ExecutorRegistry
from xushi.models import Action, Executor


class RecordingHandler(BaseHTTPRequestHandler):
    """记录 webhook 请求的测试处理器。"""

    received: ClassVar[list[dict[str, Any]]] = []

    def do_POST(self) -> None:
        """接收 POST 请求。"""
        length = int(self.headers.get("content-length", "0"))
        raw_body = self.rfile.read(length)
        self.__class__.received.append(
            {
                "path": self.path,
                "authorization": self.headers.get("authorization"),
                "body": json.loads(raw_body.decode("utf-8")),
            }
        )
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"accepted": true, "run_id": "remote_1"}')

    def log_message(self, format: str, *args: object) -> None:
        """禁用测试日志输出。"""


def _start_server() -> tuple[HTTPServer, str]:
    RecordingHandler.received = []
    server = HTTPServer(("127.0.0.1", 0), RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}/hooks/agent"


def test_webhook_executor_is_reserved_not_implemented() -> None:
    executor = Executor(
        id="webhook_agent",
        kind="webhook",
        name="Webhook Agent",
        config={"webhook_url": "http://127.0.0.1:9/hooks"},
    )
    action = Action(type="agent", executor_id="webhook_agent", payload={"prompt": "生成日报"})

    result = ExecutorRegistry().execute(action, executor)

    assert result["delivered"] is False
    assert result["executor"] == "webhook_agent"
    assert result["kind"] == "webhook"
    assert result["error"] == "webhook executor reserved but not implemented"


def test_reminder_with_executor_posts_to_agent_webhook() -> None:
    server, url = _start_server()
    try:
        executor = Executor(
            id="openclaw",
            kind="openclaw",
            name="OpenClaw",
            config={"webhook_url": url, "token": "secret", "channel": "feishu"},
        )
        action = Action(
            type="reminder",
            executor_id="openclaw",
            payload={"title": "喝水", "message": "该喝水了", "task_id": "task_1"},
        )

        result = ExecutorRegistry().execute(action, executor)
    finally:
        server.shutdown()
        server.server_close()

    assert result["delivered"] is True
    assert result["executor"] == "openclaw"
    assert result["mode"] == "hooks_agent"
    assert RecordingHandler.received[0]["authorization"] == "Bearer secret"
    body = RecordingHandler.received[0]["body"]
    assert body["name"] == "xushi"
    assert body["deliver"] is True
    assert body["channel"] == "feishu"
    assert body["wakeMode"] == "now"
    assert body["timeoutSeconds"] == 120
    assert "喝水" in body["message"]
    assert "该喝水了" in body["message"]
    assert "task_1" in body["message"]


def test_reminder_with_missing_executor_fails_instead_of_local_fallback() -> None:
    action = Action(
        type="reminder",
        executor_id="missing",
        payload={"title": "喝水", "message": "该喝水了"},
    )

    result = ExecutorRegistry().execute(action, executor=None)

    assert result["delivered"] is False
    assert result["error"] == "executor not found"


def test_openclaw_executor_uses_token_env_for_hooks_agent(monkeypatch) -> None:
    server, url = _start_server()
    monkeypatch.setenv("OPENCLAW_HOOKS_TOKEN", "secret-from-env")
    try:
        executor = Executor(
            id="openclaw",
            kind="openclaw",
            name="OpenClaw",
            config={"webhook_url": url, "token_env": "OPENCLAW_HOOKS_TOKEN"},
        )
        action = Action(type="agent", executor_id="openclaw", payload={"prompt": "提醒我喝水"})

        result = ExecutorRegistry().execute(action, executor)
    finally:
        server.shutdown()
        server.server_close()

    assert result["delivered"] is True
    assert RecordingHandler.received[0]["authorization"] == "Bearer secret-from-env"
    assert RecordingHandler.received[0]["body"]["message"] == "提醒我喝水"


def test_openclaw_executor_keeps_tls_verification_by_default(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 200

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"accepted": true}'

    def fake_urlopen(
        req: request.Request,
        timeout: int,
        context: ssl.SSLContext | None = None,
    ) -> FakeResponse:
        captured["context"] = context
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("xushi.executors.request.urlopen", fake_urlopen)
    executor = Executor(
        id="openclaw",
        kind="openclaw",
        name="OpenClaw",
        config={
            "webhook_url": "https://127.0.0.1:18789/hooks/agent",
            "token": "secret",
        },
    )
    action = Action(type="reminder", executor_id="openclaw", payload={"message": "提醒"})

    result = ExecutorRegistry().execute(action, executor)

    assert result["delivered"] is True
    assert captured["context"] is None


def test_openclaw_executor_allows_explicit_insecure_tls(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 200

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"accepted": true}'

    def fake_urlopen(
        req: request.Request,
        timeout: int,
        context: ssl.SSLContext | None = None,
    ) -> FakeResponse:
        captured["context"] = context
        return FakeResponse()

    monkeypatch.setattr("xushi.executors.request.urlopen", fake_urlopen)
    executor = Executor(
        id="openclaw",
        kind="openclaw",
        name="OpenClaw",
        config={
            "webhook_url": "https://127.0.0.1:18789/hooks/agent",
            "token": "secret",
            "insecure_tls": True,
        },
    )
    action = Action(type="reminder", executor_id="openclaw", payload={"message": "提醒"})

    result = ExecutorRegistry().execute(action, executor)

    assert result["delivered"] is True
    assert isinstance(captured["context"], ssl.SSLContext)


def test_openclaw_executor_rejects_non_hooks_agent_mode() -> None:
    executor = Executor(id="openclaw", kind="openclaw", name="OpenClaw", config={"mode": "command"})
    action = Action(type="agent", executor_id="openclaw", payload={"prompt": "整理日程"})

    result = ExecutorRegistry().execute(action, executor)

    assert result["delivered"] is False
    assert result["mode"] == "command"
    assert result["error"] == "unsupported openclaw executor mode: command"


def test_hermes_executor_posts_to_agent_webhook(monkeypatch) -> None:
    server, url = _start_server()
    monkeypatch.setenv("HERMES_API_TOKEN", "hermes-secret")
    try:
        executor = Executor(
            id="hermes",
            kind="hermes",
            name="Hermes",
            config={
                "mode": "agent_webhook",
                "webhook_url": url,
                "token_env": "HERMES_API_TOKEN",
                "message_field": "message",
                "agent_id": "planner",
                "conversation_id": "conv_1",
                "channel": "feishu",
            },
        )
        action = Action(
            type="reminder",
            executor_id="hermes",
            payload={
                "title": "整理日程",
                "message": "今晚复盘明天计划",
                "task_id": "task_hermes",
            },
        )

        result = ExecutorRegistry().execute(action, executor)
    finally:
        server.shutdown()
        server.server_close()

    assert result["delivered"] is True
    assert result["executor"] == "hermes"
    assert result["kind"] == "hermes"
    assert result["mode"] == "agent_webhook"
    assert RecordingHandler.received[0]["authorization"] == "Bearer hermes-secret"
    body = RecordingHandler.received[0]["body"]
    assert "整理日程" in body["message"]
    assert "今晚复盘明天计划" in body["message"]
    assert body["source"] == "xushi"
    assert body["metadata"]["task_id"] == "task_hermes"
    assert body["agent_id"] == "planner"
    assert body["conversation_id"] == "conv_1"
    assert body["channel"] == "feishu"


def test_hermes_executor_requires_webhook_url() -> None:
    executor = Executor(id="hermes", kind="hermes", name="Hermes", config={})
    action = Action(type="agent", executor_id="hermes", payload={"prompt": "整理日程"})

    result = ExecutorRegistry().execute(action, executor)

    assert result["delivered"] is False
    assert result["error"] == "hermes agent_webhook executor missing webhook_url"
