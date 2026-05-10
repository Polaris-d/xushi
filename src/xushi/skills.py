"""随应用版本携带的 xushi-skills 安装器。"""

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

SKILL_NAME = "xushi-skills"
INSTALL_MANIFEST = ".xushi-skill-install.json"
SUPPORTED_TARGETS = ("openclaw", "hermes")


@dataclass(frozen=True)
class SkillTarget:
    """一个 agent skills 安装目标。"""

    name: str
    skills_dir: Path

    @property
    def target_dir(self) -> Path:
        """返回 xushi-skills 的最终目录。"""
        return self.skills_dir / SKILL_NAME


def install_bundled_skills(
    targets: str,
    *,
    openclaw_skills_dir: Path | None = None,
    hermes_skills_dir: Path | None = None,
) -> dict[str, Any]:
    """将当前应用内置的 xushi-skills 安装到指定 agent。"""
    installed = []
    for target in resolve_targets(
        targets,
        openclaw_skills_dir=openclaw_skills_dir,
        hermes_skills_dir=hermes_skills_dir,
    ):
        installed.append(_install_target(target))
    return {
        "app_version": __version__,
        "skill_name": SKILL_NAME,
        "source": "bundled",
        "installed": installed,
    }


def bundled_skills_status(
    targets: str = "openclaw,hermes",
    *,
    openclaw_skills_dir: Path | None = None,
    hermes_skills_dir: Path | None = None,
) -> dict[str, Any]:
    """返回当前内置 skills 与目标目录的安装状态。"""
    return {
        "app_version": __version__,
        "skill_name": SKILL_NAME,
        "source": "bundled",
        "targets": [
            _target_status(target)
            for target in resolve_targets(
                targets,
                openclaw_skills_dir=openclaw_skills_dir,
                hermes_skills_dir=hermes_skills_dir,
            )
        ],
    }


def resolve_targets(
    targets: str,
    *,
    openclaw_skills_dir: Path | None = None,
    hermes_skills_dir: Path | None = None,
) -> list[SkillTarget]:
    """解析命令行 target 字符串为安装目标。"""
    resolved: list[SkillTarget] = []
    for raw_target in targets.split(","):
        target = raw_target.strip().lower()
        if not target:
            continue
        if target == "openclaw":
            resolved.append(
                SkillTarget(
                    name="openclaw",
                    skills_dir=_openclaw_skills_dir(openclaw_skills_dir),
                )
            )
        elif target == "hermes":
            resolved.append(
                SkillTarget(
                    name="hermes",
                    skills_dir=_hermes_skills_dir(hermes_skills_dir),
                )
            )
        else:
            raise ValueError(f"unsupported skills target: {raw_target}")
    if not resolved:
        raise ValueError("no skills targets provided")
    return resolved


def bundled_skill_files() -> Traversable:
    """返回当前应用内置的 xushi-skills 目录。"""
    source = resources.files("xushi").joinpath("bundled_skills", SKILL_NAME)
    if not source.joinpath("SKILL.md").is_file():
        raise FileNotFoundError("bundled xushi-skills is missing SKILL.md")
    return source


def _install_target(target: SkillTarget) -> dict[str, Any]:
    target.skills_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    temp_dir = target.skills_dir / f".{SKILL_NAME}-install-{timestamp}"
    backup_dir: Path | None = None
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    _copy_traversable_tree(bundled_skill_files(), temp_dir)

    if target.target_dir.exists():
        backup_dir = target.skills_dir / f"{SKILL_NAME}.backup-{timestamp}"
        counter = 2
        while backup_dir.exists():
            backup_dir = target.skills_dir / f"{SKILL_NAME}.backup-{timestamp}-{counter}"
            counter += 1
        shutil.move(str(target.target_dir), backup_dir)

    shutil.move(str(temp_dir), target.target_dir)
    _write_install_manifest(target)
    return {
        "target": target.name,
        "skills_dir": str(target.skills_dir),
        "path": str(target.target_dir),
        "installed_version": __version__,
        "backup_path": str(backup_dir) if backup_dir else None,
    }


def _target_status(target: SkillTarget) -> dict[str, Any]:
    manifest_path = target.target_dir / INSTALL_MANIFEST
    manifest = _read_json(manifest_path)
    return {
        "target": target.name,
        "skills_dir": str(target.skills_dir),
        "path": str(target.target_dir),
        "installed": (target.target_dir / "SKILL.md").exists(),
        "installed_version": manifest.get("app_version"),
        "bundled_version": __version__,
        "manifest_path": str(manifest_path),
    }


def _write_install_manifest(target: SkillTarget) -> None:
    payload = {
        "skill_name": SKILL_NAME,
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
        if item.name == "__pycache__" or item.name.endswith((".pyc", ".pyo")):
            continue
        destination = target / item.name
        if item.is_dir():
            _copy_traversable_tree(item, destination)
        else:
            with item.open("rb") as source_file:
                destination.write_bytes(source_file.read())


def _openclaw_skills_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if value := os.environ.get("XUSHI_OPENCLAW_SKILLS_DIR") or os.environ.get(
        "OPENCLAW_SKILLS_DIR"
    ):
        return Path(value)
    return Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw")) / "skills"


def _hermes_skills_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if value := os.environ.get("XUSHI_HERMES_SKILLS_DIR") or os.environ.get(
        "HERMES_SKILLS_DIR"
    ):
        return Path(value)
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "skills"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
