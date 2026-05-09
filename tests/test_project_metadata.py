"""开源项目元信息测试。"""

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_readme_has_github_friendly_install_entrypoints() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert '<p align="center">' in readme
    assert "给人类看的" in readme
    assert "Install and configure xushi by following the instructions here:" in readme
    assert (
        "https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/docs/guide/"
        "installation.md"
    ) in readme
    assert "scripts/install.ps1" in readme
    assert "scripts/install.sh" in readme


def test_license_is_mit_for_open_source_distribution() -> None:
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")

    assert "MIT License" in license_text
    assert "xushi contributors" in license_text


def test_installation_guide_is_agent_readable() -> None:
    guide = (ROOT / "docs" / "guide" / "installation.md").read_text(encoding="utf-8")

    assert "# Installation" in guide
    assert "## 给人类看的" in guide
    assert "## For LLM Agents" in guide
    assert "xushi doctor" in guide


def test_install_scripts_use_safe_defaults() -> None:
    ps1 = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")
    sh = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")

    assert "$env:USERPROFILE" in ps1
    assert "XUSHI_INSTALL_DIR" in sh
    assert "git pull --ff-only" in ps1
    assert "git pull --ff-only" in sh
    assert "uv sync" in ps1
    assert "uv sync" in sh
