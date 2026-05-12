"""CLI 测试。"""

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

import xushi.cli as cli
from xushi.cli import app
from xushi.config import Settings
from xushi.models import Executor, Schedule, TaskCreate
from xushi.service import XushiService


class FakeTextStream:
    """记录文本流 reconfigure 调用。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def reconfigure(self, **kwargs: str) -> None:
        """模拟 TextIOWrapper.reconfigure。"""
        self.calls.append(kwargs)


def test_cli_configures_standard_streams_for_utf8_help(monkeypatch) -> None:
    """CLI help 中包含中文时应使用 UTF-8 输出。"""
    stdout = FakeTextStream()
    stderr = FakeTextStream()
    monkeypatch.setattr(cli.sys, "stdout", stdout)
    monkeypatch.setattr(cli.sys, "stderr", stderr)

    cli.configure_text_output_encoding()

    assert stdout.calls == [{"encoding": "utf-8", "errors": "replace"}]
    assert stderr.calls == [{"encoding": "utf-8", "errors": "replace"}]


def test_cli_lists_notifications(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "xushi.db"
    monkeypatch.setenv("XUSHI_DATABASE_PATH", str(database_path))
    service = XushiService(Settings(database_path=database_path, api_token="test-token"))
    task = service.create_task(
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
    service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))

    result = CliRunner().invoke(app, ["notifications"])

    assert result.exit_code == 0
    assert "喝水" in result.output


def test_cli_lists_deliveries(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "xushi.db"
    monkeypatch.setenv("XUSHI_DATABASE_PATH", str(database_path))
    service = XushiService(Settings(database_path=database_path, api_token="test-token"))
    task = service.create_task(
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
    service.trigger_task(task.id, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))

    result = CliRunner().invoke(app, ["deliveries"])

    assert result.exit_code == 0
    assert "delivered" in result.output
    assert task.id in result.output


def test_cli_retry_deliveries_requeues_failed_delivery(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "xushi.db"
    monkeypatch.setenv("XUSHI_DATABASE_PATH", str(database_path))
    monkeypatch.delenv("OPENCLAW_HOOKS_TOKEN", raising=False)
    monkeypatch.delenv("OPENCLAW_WEBHOOK_TOKEN", raising=False)
    service = XushiService(
        Settings(
            database_path=database_path,
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
    failed_delivery = service.list_deliveries()[0]

    result = CliRunner().invoke(app, ["retry-deliveries"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert len(payload) == 1
    assert payload[0]["status"] == "failed"
    assert payload[0]["result"]["retry_of"] == failed_delivery.id


def test_cli_reload_config_posts_to_running_daemon(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "api_token": "test-token",
                "host": "127.0.0.1",
                "port": 18766,
                "database_path": str(tmp_path / "xushi.db"),
            }
        ),
        encoding="utf-8",
    )
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "status": 200,
                    "code": 200,
                    "message": "ok",
                    "data": {"reloaded": ["executors", "quiet_policy"]},
                    "errors": [],
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout: int):
        requests.append((req.full_url, req.headers["Authorization"], req.data, timeout))
        return FakeResponse()

    monkeypatch.setattr("xushi.cli.request.urlopen", fake_urlopen)

    result = CliRunner().invoke(app, ["reload-config", "--config-path", str(config_path)])

    assert result.exit_code == 0
    assert requests == [
        (
            "http://127.0.0.1:18766/api/v1/config/reload",
            "Bearer test-token",
            b"",
            10,
        )
    ]
    assert json.loads(result.output)["data"]["reloaded"] == ["executors", "quiet_policy"]


def test_cli_reload_config_does_not_validate_runtime_config_before_request(
    tmp_path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "api_token": "test-token",
                "host": "127.0.0.1",
                "port": 18766,
                "database_path": str(tmp_path / "xushi.db"),
                "executors": [{"id": "bad", "kind": "command", "config": {}}],
            }
        ),
        encoding="utf-8",
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "status": 400,
                    "code": 400,
                    "message": "config reload failed",
                    "data": None,
                    "errors": [{"detail": "config reload failed"}],
                }
            ).encode("utf-8")

    monkeypatch.setattr("xushi.cli.request.urlopen", lambda *_args, **_kwargs: FakeResponse())

    result = CliRunner().invoke(app, ["reload-config", "--config-path", str(config_path)])

    assert result.exit_code == 0
    assert json.loads(result.output)["message"] == "config reload failed"


def test_cli_installs_bundled_skills(tmp_path) -> None:
    openclaw_dir = tmp_path / "openclaw-skills"
    hermes_dir = tmp_path / "hermes-skills"

    result = CliRunner().invoke(
        app,
        [
            "skills",
            "install",
            "--targets",
            "openclaw,hermes",
            "--openclaw-skills-dir",
            str(openclaw_dir),
            "--hermes-skills-dir",
            str(hermes_dir),
        ],
    )

    assert result.exit_code == 0
    assert (openclaw_dir / "xushi-skills" / "SKILL.md").exists()
    assert (hermes_dir / "xushi-skills" / "SKILL.md").exists()
    assert "bundled" in result.output


def test_cli_reports_bundled_skills_status(tmp_path) -> None:
    openclaw_dir = tmp_path / "openclaw-skills"

    install_result = CliRunner().invoke(
        app,
        [
            "skills",
            "install",
            "--targets",
            "openclaw",
            "--openclaw-skills-dir",
            str(openclaw_dir),
        ],
    )
    assert install_result.exit_code == 0

    result = CliRunner().invoke(
        app,
        [
            "skills",
            "status",
            "--targets",
            "openclaw",
            "--openclaw-skills-dir",
            str(openclaw_dir),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["source"] == "bundled"
    assert payload["targets"][0]["installed"] is True
    assert payload["targets"][0]["installed_version"] == payload["app_version"]


def test_cli_installs_bundled_openclaw_plugin(tmp_path) -> None:
    plugins_dir = tmp_path / "openclaw-plugins"

    result = CliRunner().invoke(
        app,
        [
            "plugins",
            "install",
            "openclaw",
            "--openclaw-plugins-dir",
            str(plugins_dir),
        ],
    )

    assert result.exit_code == 0
    assert (plugins_dir / "openclaw-xushi" / "openclaw.plugin.json").exists()
    assert (plugins_dir / "openclaw-xushi" / "dist" / "index.js").exists()
    assert "bundled" in result.output


def test_cli_reports_bundled_openclaw_plugin_status(tmp_path) -> None:
    plugins_dir = tmp_path / "openclaw-plugins"

    install_result = CliRunner().invoke(
        app,
        [
            "plugins",
            "install",
            "openclaw",
            "--openclaw-plugins-dir",
            str(plugins_dir),
        ],
    )
    assert install_result.exit_code == 0

    result = CliRunner().invoke(
        app,
        [
            "plugins",
            "status",
            "openclaw",
            "--openclaw-plugins-dir",
            str(plugins_dir),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["source"] == "bundled"
    assert payload["installed"] is True
    assert payload["installed_version"] == payload["app_version"]


def test_cli_init_writes_config_without_printing_full_token(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    state_dir = tmp_path / "state"

    result = CliRunner().invoke(
        app,
        [
            "init",
            "--config-path",
            str(config_path),
            "--state-dir",
            str(state_dir),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["api_token"] not in result.output
    assert "config.json" in result.output
    assert payload["database_path"] == str(state_dir / "xushi.db")


def test_cli_doctor_reports_config_and_database_path(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    state_dir = tmp_path / "state"
    init_result = CliRunner().invoke(
        app,
        [
            "init",
            "--config-path",
            str(config_path),
            "--state-dir",
            str(state_dir),
        ],
    )
    assert init_result.exit_code == 0

    result = CliRunner().invoke(app, ["doctor", "--config-path", str(config_path)])

    assert result.exit_code == 0
    report = json.loads(result.output)
    assert report["config_path"] == str(config_path)
    assert report["database_path"] == str(state_dir / "xushi.db")
    assert "api_token" in report
    assert report["executors"][0]["id"] == "openclaw"
    assert "diagnostics" in report["executors"][0]


def test_cli_doctor_warns_about_openclaw_token_and_agent_id(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OPENCLAW_HOOKS_TOKEN", raising=False)
    config_path = tmp_path / "config.json"
    state_dir = tmp_path / "state"
    init_result = CliRunner().invoke(
        app,
        [
            "init",
            "--config-path",
            str(config_path),
            "--state-dir",
            str(state_dir),
        ],
    )
    assert init_result.exit_code == 0

    result = CliRunner().invoke(app, ["doctor", "--config-path", str(config_path)])

    assert result.exit_code == 0
    report = json.loads(result.output)
    diagnostics = report["executors"][0]["diagnostics"]
    assert "token_env_not_present_in_process:OPENCLAW_HOOKS_TOKEN" in diagnostics
    assert "agent_id_missing_routes_to_openclaw_default_agent" in diagnostics


def test_cli_upgrade_status_reports_local_paths(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    state_dir = tmp_path / "state"
    init_result = CliRunner().invoke(
        app,
        [
            "init",
            "--config-path",
            str(config_path),
            "--state-dir",
            str(state_dir),
        ],
    )
    assert init_result.exit_code == 0
    monkeypatch.setenv("XUSHI_CONFIG_PATH", str(config_path))

    result = CliRunner().invoke(app, ["upgrade", "status"])

    assert result.exit_code == 0
    report = json.loads(result.output)
    assert report["config_path"] == str(config_path)
    assert report["database_path"] == str(state_dir / "xushi.db")
    assert report["backups"] == []


def test_cli_upgrade_backup_creates_manual_backup(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    state_dir = tmp_path / "state"
    init_result = CliRunner().invoke(
        app,
        [
            "init",
            "--config-path",
            str(config_path),
            "--state-dir",
            str(state_dir),
        ],
    )
    assert init_result.exit_code == 0
    monkeypatch.setenv("XUSHI_CONFIG_PATH", str(config_path))

    result = CliRunner().invoke(app, ["upgrade", "backup"])

    assert result.exit_code == 0
    report = json.loads(result.output)
    assert report["id"].startswith("upgrade-")
    assert (Path(report["path"]) / "config.json").exists()
