"""检查发布元数据与内置资源是否保持一致。"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def main() -> int:
    """执行元数据一致性检查。"""
    errors: list[str] = []
    app_version = _pyproject_version()
    manifest = json.loads(
        (ROOT / "plugins" / "openclaw-xushi" / "openclaw.plugin.json").read_text(
            encoding="utf-8"
        )
    )
    package = json.loads(
        (ROOT / "plugins" / "openclaw-xushi" / "package.json").read_text(
            encoding="utf-8"
        )
    )

    if manifest["version"] != app_version:
        errors.append("openclaw.plugin.json version does not match pyproject.toml")
    if package["version"] != app_version:
        errors.append("package.json version does not match pyproject.toml")

    errors.extend(
        _compare_tree(
            "xushi-skills",
            ROOT / "skills" / "xushi-skills",
            ROOT / "src" / "xushi" / "bundled_skills" / "xushi-skills",
        )
    )
    errors.extend(
        _compare_tree(
            "openclaw-xushi",
            ROOT / "plugins" / "openclaw-xushi",
            ROOT / "src" / "xushi" / "bundled_plugins" / "openclaw-xushi",
        )
    )

    if errors:
        for error in errors:
            print(f"metadata check failed: {error}", file=sys.stderr)
        return 1
    print("project metadata is consistent")
    return 0


def _pyproject_version() -> str:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(pyproject["project"]["version"])


def _compare_tree(name: str, source_root: Path, bundled_root: Path) -> list[str]:
    errors: list[str] = []
    source_files = _files(source_root)
    bundled_files = _files(bundled_root)
    if source_files != bundled_files:
        errors.append(f"{name} bundled file list differs")
        return errors
    for relative_path in source_files:
        source = (source_root / relative_path).read_text(encoding="utf-8")
        bundled = (bundled_root / relative_path).read_text(encoding="utf-8")
        if source != bundled:
            errors.append(f"{name}/{relative_path.as_posix()} differs from bundled copy")
    return errors


def _files(root: Path) -> list[Path]:
    return sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())


if __name__ == "__main__":
    raise SystemExit(main())
