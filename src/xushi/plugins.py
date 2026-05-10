"""随应用版本携带的 OpenClaw 插件安装器。"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from xushi import __version__

PLUGIN_NAME = "openclaw-xushi"
INSTALL_DIR_NAME = "openclaw-xushi"
INSTALL_MANIFEST = ".xushi-plugin-install.json"
SUPPORTED_TARGETS = ("openclaw",)


@dataclass(frozen=True)
class PluginTarget:
    """一个 agent plugin 安装目标。"""

    name: str
    plugins_dir: Path

    @property
    def target_dir(self) -> Path:
        """返回插件最终目录。"""
        return self.plugins_dir / INSTALL_DIR_NAME


def install_bundled_plugin(
    target_name: str,
    *,
    openclaw_plugins_dir: Path | None = None,
) -> dict[str, Any]:
    """将当前应用内置插件安装到指定 agent。"""
    target = resolve_plugin_target(target_name, openclaw_plugins_dir=openclaw_plugins_dir)
    return {
        "app_version": __version__,
        "plugin_name": PLUGIN_NAME,
        "source": "bundled",
        "installed": _install_target(target),
    }


def bundled_plugin_status(
    target_name: str = "openclaw",
    *,
    openclaw_plugins_dir: Path | None = None,
) -> dict[str, Any]:
    """返回当前内置插件与目标目录的安装状态。"""
    target = resolve_plugin_target(target_name, openclaw_plugins_dir=openclaw_plugins_dir)
    manifest_path = target.target_dir / INSTALL_MANIFEST
    manifest = _read_json(manifest_path)
    return {
        "app_version": __version__,
        "plugin_name": PLUGIN_NAME,
        "source": "bundled",
        "target": target.name,
        "plugins_dir": str(target.plugins_dir),
        "path": str(target.target_dir),
        "installed": (target.target_dir / "openclaw.plugin.json").exists(),
        "installed_version": manifest.get("app_version"),
        "bundled_version": __version__,
        "manifest_path": str(manifest_path),
    }


def resolve_plugin_target(
    target_name: str,
    *,
    openclaw_plugins_dir: Path | None = None,
) -> PluginTarget:
    """解析插件安装目标。"""
    target = target_name.strip().lower()
    if target != "openclaw":
        raise ValueError(f"unsupported plugin target: {target_name}")
    return PluginTarget(name="openclaw", plugins_dir=_openclaw_plugins_dir(openclaw_plugins_dir))


def bundled_plugin_files() -> Traversable:
    """返回当前应用内置 OpenClaw 插件目录。"""
    source = resources.files("xushi").joinpath("bundled_plugins", PLUGIN_NAME)
    if not source.joinpath("openclaw.plugin.json").is_file():
        raise FileNotFoundError("bundled OpenClaw plugin is missing openclaw.plugin.json")
    return source


def _install_target(target: PluginTarget) -> dict[str, Any]:
    target.plugins_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    temp_dir = target.plugins_dir / f".{INSTALL_DIR_NAME}-install-{timestamp}"
    backup_dir: Path | None = None
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    _copy_traversable_tree(bundled_plugin_files(), temp_dir)

    if target.target_dir.exists():
        backup_dir = target.plugins_dir / f"{INSTALL_DIR_NAME}.backup-{timestamp}"
        counter = 2
        while backup_dir.exists():
            backup_dir = target.plugins_dir / f"{INSTALL_DIR_NAME}.backup-{timestamp}-{counter}"
            counter += 1
        shutil.move(str(target.target_dir), backup_dir)

    shutil.move(str(temp_dir), target.target_dir)
    _write_install_manifest(target)
    return {
        "target": target.name,
        "plugins_dir": str(target.plugins_dir),
        "path": str(target.target_dir),
        "installed_version": __version__,
        "backup_path": str(backup_dir) if backup_dir else None,
    }


def _write_install_manifest(target: PluginTarget) -> None:
    payload = {
        "plugin_name": PLUGIN_NAME,
        "app_version": __version__,
        "target": target.name,
        "installed_at": datetime.now(tz=UTC).isoformat(),
        "source": "bundled",
    }
    (target.target_dir / INSTALL_MANIFEST).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _copy_traversable_tree(source: Traversable, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name in {"node_modules", "__pycache__"} or item.name.endswith((".pyc", ".pyo")):
            continue
        destination = target / item.name
        if item.is_dir():
            _copy_traversable_tree(item, destination)
        else:
            with item.open("rb") as source_file:
                destination.write_bytes(source_file.read())


def _openclaw_plugins_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if value := os.environ.get("XUSHI_OPENCLAW_PLUGINS_DIR") or os.environ.get(
        "OPENCLAW_PLUGINS_DIR"
    ):
        return Path(value)
    return Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw")) / "plugins"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
