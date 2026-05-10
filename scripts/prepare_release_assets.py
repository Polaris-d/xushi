"""准备 GitHub Release 资产。"""

from __future__ import annotations

import argparse
import platform
import shutil
import sys
import zipfile
from pathlib import Path

BINARY_NAMES = ("xushi", "xushi-daemon")
EXCLUDED_PLUGIN_PARTS = {".git", "node_modules", "__pycache__"}
EXCLUDED_SKILL_PARTS = {".git", "__pycache__"}


def normalize_platform_tag(system: str | None = None, machine: str | None = None) -> str:
    """生成稳定的平台标签。"""
    raw_system = (system or platform.system()).lower()
    raw_machine = (machine or platform.machine()).lower()
    os_name = {
        "darwin": "macos",
        "windows": "windows",
        "linux": "linux",
    }.get(raw_system, raw_system)
    arch_name = {
        "amd64": "x64",
        "x86_64": "x64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }.get(raw_machine, raw_machine)
    return f"{os_name}-{arch_name}"


def copy_binary_assets(
    dist_dir: Path,
    output_dir: Path,
    platform_tag: str | None = None,
) -> list[Path]:
    """复制二进制产物，并按平台重命名。"""
    resolved_platform_tag = platform_tag or normalize_platform_tag()
    output_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for binary_name in BINARY_NAMES:
        source = _find_binary(dist_dir, binary_name)
        suffix = source.suffix if source.suffix == ".exe" else ""
        target = output_dir / f"{binary_name}-{resolved_platform_tag}{suffix}"
        shutil.copy2(source, target)
        copied.append(target)
    return copied


def copy_python_dist(dist_dir: Path, output_dir: Path) -> list[Path]:
    """复制 Python wheel 和 sdist。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for pattern in ("*.whl", "*.tar.gz"):
        for source in sorted(dist_dir.glob(pattern)):
            target = output_dir / source.name
            shutil.copy2(source, target)
            copied.append(target)
    if not copied:
        raise FileNotFoundError(f"未在 {dist_dir} 找到 wheel 或 sdist")
    return copied


def package_openclaw_plugin(plugin_dir: Path, output_dir: Path) -> Path:
    """打包 OpenClaw 插件目录。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / "xushi-openclaw-plugin.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for source in sorted(path for path in plugin_dir.rglob("*") if path.is_file()):
            relative_path = source.relative_to(plugin_dir)
            if _should_skip_plugin_file(relative_path):
                continue
            zip_file.write(source, relative_path.as_posix())
    return archive


def package_xushi_skills(skill_dir: Path, output_dir: Path) -> Path:
    """打包 xushi agent skills。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / "xushi-skills.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for source in sorted(path for path in skill_dir.rglob("*") if path.is_file()):
            relative_path = source.relative_to(skill_dir.parent)
            if _should_skip_skill_file(relative_path):
                continue
            zip_file.write(source, relative_path.as_posix())
    return archive


def _find_binary(dist_dir: Path, binary_name: str) -> Path:
    """查找 PyInstaller 输出的单文件二进制。"""
    candidates = (dist_dir / binary_name, dist_dir / f"{binary_name}.exe")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"未在 {dist_dir} 找到 {binary_name} 二进制")


def _should_skip_plugin_file(relative_path: Path) -> bool:
    """判断插件打包时是否应跳过文件。"""
    if any(part in EXCLUDED_PLUGIN_PARTS for part in relative_path.parts):
        return True
    return relative_path.suffix in {".pyc", ".pyo"}


def _should_skip_skill_file(relative_path: Path) -> bool:
    """判断 skill 打包时是否应跳过文件。"""
    if any(part in EXCLUDED_SKILL_PARTS for part in relative_path.parts):
        return True
    return relative_path.suffix in {".pyc", ".pyo"}


def _resolve_path(project_root: Path, value: str | None, default: Path) -> Path:
    """解析命令行路径。"""
    if value is None:
        return default
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def main(argv: list[str] | None = None) -> int:
    """执行 release 资产准备。"""
    parser = argparse.ArgumentParser(description="准备 xushi GitHub Release 资产")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="项目根目录",
    )
    parser.add_argument("--dist-dir", help="构建产物目录, 默认使用 <project-root>/dist")
    parser.add_argument(
        "--output-dir",
        help="release 资产输出目录, 默认使用 <project-root>/release-assets",
    )
    parser.add_argument("--platform-tag", help="二进制平台标签, 例如 linux-x64")
    parser.add_argument("--python-dist", action="store_true", help="复制 wheel 和 sdist")
    parser.add_argument("--binaries", action="store_true", help="复制并重命名二进制")
    parser.add_argument("--plugin", action="store_true", help="打包 OpenClaw 插件")
    parser.add_argument("--skills", action="store_true", help="打包 xushi agent skills")
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()
    dist_dir = _resolve_path(project_root, args.dist_dir, project_root / "dist")
    output_dir = _resolve_path(project_root, args.output_dir, project_root / "release-assets")
    selected = args.python_dist or args.binaries or args.plugin or args.skills
    include_python_dist = args.python_dist or not selected
    include_binaries = args.binaries or not selected
    include_plugin = args.plugin or not selected
    include_skills = args.skills or not selected

    assets: list[Path] = []
    if include_python_dist:
        assets.extend(copy_python_dist(dist_dir=dist_dir, output_dir=output_dir))
    if include_binaries:
        assets.extend(
            copy_binary_assets(
                dist_dir=dist_dir,
                output_dir=output_dir,
                platform_tag=args.platform_tag,
            )
        )
    if include_plugin:
        assets.append(
            package_openclaw_plugin(
                plugin_dir=project_root / "plugins" / "openclaw-xushi",
                output_dir=output_dir,
            )
        )
    if include_skills:
        assets.append(
            package_xushi_skills(
                skill_dir=project_root / "skills" / "xushi-skills",
                output_dir=output_dir,
            )
        )

    for asset in assets:
        print(asset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
