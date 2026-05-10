"""分发构建脚本测试。"""

import importlib.util
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


def test_release_asset_script_does_not_publish_standalone_plugin_zip() -> None:
    module = _load_prepare_release_assets_module()

    assert not hasattr(module, "package_openclaw_plugin")


def test_release_asset_script_does_not_publish_standalone_skills_zip() -> None:
    module = _load_prepare_release_assets_module()

    assert not hasattr(module, "package_xushi_skills")
