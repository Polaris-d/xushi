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


def test_pyinstaller_commands_collect_xushi_package_data() -> None:
    build_commands = _load_build_binaries_module().build_commands
    commands = build_commands(project_root=Path("repo"))

    assert commands
    assert all("--collect-data" in command for command in commands)
    assert all("xushi" in command for command in commands)
    assert any("--name=xushi-daemon" in command for command in commands)
    assert any("--name=xushi" in command for command in commands)
