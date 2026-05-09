"""序时配置。"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766
DEFAULT_SCHEDULER_INTERVAL_SECONDS = 30
DEFAULT_DEV_TOKEN = "dev-token"


def default_state_dir() -> Path:
    """返回默认本地状态目录。"""
    return Path(os.environ.get("XUSHI_STATE_DIR", Path.home() / ".xushi"))


def default_config_path() -> Path:
    """返回默认配置文件路径。"""
    return Path(os.environ.get("XUSHI_CONFIG_PATH", default_state_dir() / "config.json"))


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """读取本地配置文件，不存在时返回空配置。"""
    resolved_path = Path(config_path) if config_path else default_config_path()
    if not resolved_path.exists():
        return {}
    return json.loads(resolved_path.read_text(encoding="utf-8"))


def write_initial_config(
    config_path: Path | None = None,
    state_dir: Path | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """写入本地初始配置。

    Args:
        config_path: 配置文件路径。为空时使用默认路径。
        state_dir: 本地状态目录。为空时使用默认状态目录。
        force: 是否覆盖已有配置文件。

    Returns:
        写入磁盘的配置内容。

    Raises:
        FileExistsError: 配置文件已存在且未启用覆盖。

    """
    resolved_config_path = Path(config_path) if config_path else default_config_path()
    resolved_state_dir = Path(state_dir) if state_dir else default_state_dir()
    if resolved_config_path.exists() and not force:
        raise FileExistsError(f"配置文件已存在: {resolved_config_path}")

    resolved_config_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_state_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "api_token": secrets.token_urlsafe(32),
        "database_path": str(resolved_state_dir / "xushi.db"),
        "host": DEFAULT_HOST,
        "port": DEFAULT_PORT,
        "scheduler_interval_seconds": DEFAULT_SCHEDULER_INTERVAL_SECONDS,
    }
    resolved_config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


@dataclass(frozen=True)
class Settings:
    """应用运行配置。"""

    database_path: Path = field(default_factory=lambda: default_state_dir() / "xushi.db")
    api_token: str = DEFAULT_DEV_TOKEN
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    scheduler_interval_seconds: int = DEFAULT_SCHEDULER_INTERVAL_SECONDS

    @classmethod
    def from_env(cls, config_path: Path | None = None) -> Settings:
        """从配置文件和环境变量加载配置。"""
        file_config = load_config(config_path)
        database_path = os.environ.get(
            "XUSHI_DATABASE_PATH",
            file_config.get("database_path", default_state_dir() / "xushi.db"),
        )
        return cls(
            database_path=Path(database_path),
            api_token=os.environ.get(
                "XUSHI_API_TOKEN",
                str(file_config.get("api_token", DEFAULT_DEV_TOKEN)),
            ),
            host=os.environ.get("XUSHI_HOST", str(file_config.get("host", DEFAULT_HOST))),
            port=int(os.environ.get("XUSHI_PORT", file_config.get("port", DEFAULT_PORT))),
            scheduler_interval_seconds=int(
                os.environ.get(
                    "XUSHI_SCHEDULER_INTERVAL_SECONDS",
                    file_config.get(
                        "scheduler_interval_seconds",
                        DEFAULT_SCHEDULER_INTERVAL_SECONDS,
                    ),
                )
            ),
        )
