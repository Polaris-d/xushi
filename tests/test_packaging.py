"""分发构建脚本测试。"""

import importlib.util
import zipfile
from pathlib import Path


def _load_build_binaries_module():
    script_path = Path(__file__).parents[1] / "scripts" / "build_binaries.py"
    spec = importlib.util.spec_from_file_location("build_binaries", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_prepare_release_assets_module():
    script_path = Path(__file__).parents[1] / "scripts" / "prepare_release_assets.py"
    spec = importlib.util.spec_from_file_location("prepare_release_assets", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pyinstaller_commands_collect_xushi_package_data() -> None:
    build_commands = _load_build_binaries_module().build_commands
    commands = build_commands(project_root=Path("repo"))

    assert commands
    assert all("--collect-data" in command for command in commands)
    assert all("xushi" in command for command in commands)
    assert any("--name=xushi-daemon" in command for command in commands)
    assert any("--name=xushi" in command for command in commands)


def test_release_asset_script_names_binaries_by_platform(tmp_path) -> None:
    module = _load_prepare_release_assets_module()
    dist_dir = tmp_path / "dist"
    output_dir = tmp_path / "release-assets"
    dist_dir.mkdir()
    (dist_dir / "xushi").write_text("cli", encoding="utf-8")
    (dist_dir / "xushi-daemon").write_text("daemon", encoding="utf-8")

    copied = module.copy_binary_assets(
        dist_dir=dist_dir,
        output_dir=output_dir,
        platform_tag="linux-x64",
    )

    assert sorted(path.name for path in copied) == [
        "xushi-daemon-linux-x64",
        "xushi-linux-x64",
    ]
    assert (output_dir / "xushi-linux-x64").read_text(encoding="utf-8") == "cli"


def test_release_asset_script_packages_openclaw_plugin(tmp_path) -> None:
    module = _load_prepare_release_assets_module()
    plugin_dir = tmp_path / "plugins" / "openclaw-xushi"
    output_dir = tmp_path / "release-assets"
    (plugin_dir / "dist").mkdir(parents=True)
    (plugin_dir / "node_modules").mkdir()
    (plugin_dir / "openclaw.plugin.json").write_text("{}", encoding="utf-8")
    (plugin_dir / "dist" / "index.js").write_text("export {};", encoding="utf-8")
    (plugin_dir / "node_modules" / "ignored.js").write_text("ignored", encoding="utf-8")

    archive = module.package_openclaw_plugin(plugin_dir=plugin_dir, output_dir=output_dir)

    assert archive.name == "xushi-openclaw-plugin.zip"
    assert archive.exists()
    with zipfile.ZipFile(archive) as zip_file:
        names = zip_file.namelist()
    assert "openclaw.plugin.json" in names
    assert "dist/index.js" in names
    assert all("node_modules" not in name for name in names)


def test_release_asset_script_packages_xushi_skills(tmp_path) -> None:
    module = _load_prepare_release_assets_module()
    skill_dir = tmp_path / "skills" / "xushi-skills"
    output_dir = tmp_path / "release-assets"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "__pycache__").mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: xushi-skills\n---\n", encoding="utf-8")
    (skill_dir / "references" / "task-types.md").write_text("types", encoding="utf-8")
    (skill_dir / "__pycache__" / "ignored.pyc").write_text("ignored", encoding="utf-8")

    archive = module.package_xushi_skills(skill_dir=skill_dir, output_dir=output_dir)

    assert archive.name == "xushi-skills.zip"
    assert archive.exists()
    with zipfile.ZipFile(archive) as zip_file:
        names = zip_file.namelist()
    assert "xushi-skills/SKILL.md" in names
    assert "xushi-skills/references/task-types.md" in names
    assert all("__pycache__" not in name for name in names)
