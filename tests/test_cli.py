"""CLI 测试。"""

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from xushi.cli import app
from xushi.config import Settings
from xushi.models import Schedule, TaskCreate
from xushi.service import XushiService


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
