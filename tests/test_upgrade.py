"""手动升级安全流程测试。"""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from xushi.upgrade import UpgradeManager


def _write_database(database_path: Path, value: str) -> None:
    with sqlite3.connect(database_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS sample (value TEXT NOT NULL)")
        conn.execute("DELETE FROM sample")
        conn.execute("INSERT INTO sample (value) VALUES (?)", (value,))


def _read_database(database_path: Path) -> str:
    with sqlite3.connect(database_path) as conn:
        row = conn.execute("SELECT value FROM sample").fetchone()
    return str(row[0])


def test_upgrade_backup_preserves_config_and_sqlite_database(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    database_path = tmp_path / "xushi.db"
    config_path.write_text(json.dumps({"api_token": "secret"}), encoding="utf-8")
    _write_database(database_path, "before-upgrade")
    manager = UpgradeManager(
        config_path=config_path,
        database_path=database_path,
        state_dir=tmp_path,
        install_dir=tmp_path / "app",
    )

    backup = manager.create_backup(now=datetime(2026, 5, 10, 12, 0, tzinfo=UTC))

    assert backup.id == "upgrade-20260510T120000Z"
    assert backup.path.exists()
    assert json.loads((backup.path / "config.json").read_text(encoding="utf-8")) == {
        "api_token": "secret"
    }
    assert _read_database(backup.path / "xushi.db") == "before-upgrade"
    manifest = json.loads((backup.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["id"] == backup.id
    assert manifest["files"][0]["kind"] == "config"


def test_upgrade_rollback_restores_config_and_database(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    database_path = tmp_path / "xushi.db"
    config_path.write_text(json.dumps({"api_token": "original"}), encoding="utf-8")
    _write_database(database_path, "original-data")
    manager = UpgradeManager(
        config_path=config_path,
        database_path=database_path,
        state_dir=tmp_path,
        install_dir=tmp_path / "app",
    )
    backup = manager.create_backup(now=datetime(2026, 5, 10, 12, 0, tzinfo=UTC))
    config_path.write_text(json.dumps({"api_token": "changed"}), encoding="utf-8")
    _write_database(database_path, "changed-data")

    restored = manager.rollback(backup.id)

    assert restored.id == backup.id
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"api_token": "original"}
    assert _read_database(database_path) == "original-data"


def test_upgrade_apply_creates_backup_before_downloading_release_assets(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    database_path = tmp_path / "xushi.db"
    install_dir = tmp_path / "bin"
    config_path.write_text(json.dumps({"api_token": "secret"}), encoding="utf-8")
    _write_database(database_path, "before-upgrade")
    urls: list[str] = []

    def fake_downloader(url: str, target: Path) -> None:
        urls.append(url)
        target.write_text(url, encoding="utf-8")

    manager = UpgradeManager(
        config_path=config_path,
        database_path=database_path,
        state_dir=tmp_path,
        install_dir=install_dir,
        platform_tag="linux-x64",
        downloader=fake_downloader,
    )

    result = manager.apply(target_version="v0.1.2", allow_running_daemon=True)

    assert result.status == "succeeded"
    assert (tmp_path / "backups" / result.backup_id / "xushi.db").exists()
    assert (install_dir / "xushi").exists()
    assert (install_dir / "xushi-daemon").exists()
    assert urls == [
        "https://github.com/Polaris-d/xushi/releases/download/v0.1.2/xushi-linux-x64",
        "https://github.com/Polaris-d/xushi/releases/download/v0.1.2/xushi-daemon-linux-x64",
    ]
