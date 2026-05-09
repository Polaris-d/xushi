"""配置加载与初始化测试。"""

import json
from pathlib import Path

from xushi import config
from xushi.config import Settings


def test_default_port_avoids_blocked_windows_development_port() -> None:
    settings = Settings()

    assert settings.port == 8766


def test_write_initial_config_creates_local_token_and_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("XUSHI_API_TOKEN", raising=False)
    monkeypatch.delenv("XUSHI_CONFIG_PATH", raising=False)
    config_path = tmp_path / "config.json"
    state_dir = tmp_path / "state"

    saved = config.write_initial_config(config_path=config_path, state_dir=state_dir)

    assert config_path.exists()
    assert saved["api_token"] != "dev-token"
    assert len(saved["api_token"]) >= 32
    assert saved["database_path"] == str(state_dir / "xushi.db")
    assert saved["host"] == "127.0.0.1"
    assert saved["port"] == 8766
    assert saved["scheduler_interval_seconds"] == 30
    assert json.loads(config_path.read_text(encoding="utf-8")) == saved


def test_settings_loads_config_file_before_defaults(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    database_path = tmp_path / "custom.db"
    payload = {
        "api_token": "token-from-config",
        "database_path": str(database_path),
        "host": "127.0.0.1",
        "port": 9876,
        "scheduler_interval_seconds": 7,
    }
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("XUSHI_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("XUSHI_API_TOKEN", raising=False)
    monkeypatch.delenv("XUSHI_DATABASE_PATH", raising=False)
    monkeypatch.delenv("XUSHI_PORT", raising=False)
    monkeypatch.delenv("XUSHI_SCHEDULER_INTERVAL_SECONDS", raising=False)

    settings = Settings.from_env()

    assert settings.api_token == "token-from-config"
    assert settings.database_path == database_path
    assert settings.port == 9876
    assert settings.scheduler_interval_seconds == 7


def test_environment_variables_override_config_file(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "api_token": "token-from-config",
                "database_path": str(tmp_path / "config.db"),
                "host": "127.0.0.1",
                "port": 9876,
                "scheduler_interval_seconds": 7,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("XUSHI_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("XUSHI_API_TOKEN", "token-from-env")
    monkeypatch.setenv("XUSHI_DATABASE_PATH", str(tmp_path / "env.db"))
    monkeypatch.setenv("XUSHI_PORT", "9999")
    monkeypatch.setenv("XUSHI_SCHEDULER_INTERVAL_SECONDS", "3")

    settings = Settings.from_env()

    assert settings.api_token == "token-from-env"
    assert settings.database_path == Path(tmp_path / "env.db")
    assert settings.port == 9999
    assert settings.scheduler_interval_seconds == 3
