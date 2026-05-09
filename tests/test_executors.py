"""执行器真实调用测试。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar

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


def test_webhook_executor_posts_action_payload() -> None:
    server, url = _start_server()
    try:
        executor = Executor(
            id="webhook_agent",
            kind="webhook",
            name="Webhook Agent",
            config={"webhook_url": url, "token": "secret"},
        )
        action = Action(type="agent", executor_id="webhook_agent", payload={"prompt": "生成日报"})

        result = ExecutorRegistry().execute(action, executor)
    finally:
        server.shutdown()
        server.server_close()

    assert result["delivered"] is True
    assert result["status_code"] == 200
    assert result["response_json"] == {"accepted": True, "run_id": "remote_1"}
    assert RecordingHandler.received[0]["authorization"] == "Bearer secret"
    assert RecordingHandler.received[0]["body"]["payload"] == {"prompt": "生成日报"}


def test_openclaw_executor_delegates_to_webhook_when_configured() -> None:
    server, url = _start_server()
    try:
        executor = Executor(
            id="openclaw",
            kind="openclaw",
            name="OpenClaw",
            config={"webhook_url": url},
        )
        action = Action(type="agent", executor_id="openclaw", payload={"prompt": "提醒我喝水"})

        result = ExecutorRegistry().execute(action, executor)
    finally:
        server.shutdown()
        server.server_close()

    assert result["delivered"] is True
    assert RecordingHandler.received[0]["body"]["executor"]["kind"] == "openclaw"


def test_hermes_executor_without_command_or_webhook_fails_explicitly() -> None:
    executor = Executor(id="hermes", kind="hermes", name="Hermes", config={"mode": "template"})
    action = Action(type="agent", executor_id="hermes", payload={"prompt": "整理日程"})

    result = ExecutorRegistry().execute(action, executor)

    assert result["delivered"] is False
    assert "missing command or webhook_url" in result["error"]
