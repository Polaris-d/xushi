"""构建序时预编译二进制。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ENTRY_POINTS = (
    ("xushi-daemon", Path("packaging") / "xushi_daemon_entry.py"),
    ("xushi", Path("packaging") / "xushi_cli_entry.py"),
)


def build_commands(project_root: Path) -> list[list[str]]:
    """生成 PyInstaller 构建命令。"""
    return [
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--onefile",
            f"--name={name}",
            "--collect-data",
            "xushi",
            "--paths",
            str(project_root / "src"),
            str(project_root / entry_point),
        ]
        for name, entry_point in ENTRY_POINTS
    ]


def main(argv: list[str] | None = None) -> int:
    """执行二进制构建。"""
    parser = argparse.ArgumentParser(description="构建 xushi 预编译二进制")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="项目根目录",
    )
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()
    for command in build_commands(project_root):
        subprocess.run(command, cwd=project_root, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
