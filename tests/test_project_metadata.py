"""开源项目元信息测试。"""

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_readme_has_github_friendly_install_entrypoints() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert '<p align="center">' in readme
    assert "给人类看的" in readme
    assert "优先适配 OpenClaw 和 Hermes" in readme
    assert "Install and configure xushi by following the instructions here:" in readme
    assert (
        "https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/docs/guide/"
        "installation.md"
    ) in readme
    assert "scripts/install.ps1" in readme
    assert "scripts/install.sh" in readme
    assert "强烈推荐开启" in readme
    assert "测试提醒" in readme


def test_license_is_mit_for_open_source_distribution() -> None:
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")

    assert "MIT License" in license_text
    assert "xushi contributors" in license_text


def test_installation_guide_is_agent_readable() -> None:
    guide = (ROOT / "docs" / "guide" / "installation.md").read_text(encoding="utf-8")

    assert "# Installation" in guide
    assert "## 给人类看的" in guide
    assert "## For LLM Agents" in guide
    assert "xushi prioritizes OpenClaw and Hermes" in guide
    assert "supports `openclaw` and `hermes`" in guide
    assert "XUSHI_INSTALL_AGENT_SKILLS=openclaw,hermes" in guide
    assert "XUSHI_OPENCLAW_SKILLS_DIR" in guide
    assert "XUSHI_HERMES_SKILLS_DIR" in guide
    assert "OPENCLAW_SKILLS_DIR" in guide
    assert "HERMES_SKILLS_DIR" in guide
    assert "--openclaw-skills-dir" in guide
    assert "--hermes-skills-dir" in guide
    assert "strongly recommended" in guide
    assert "是否同时安装 OpenClaw 插件和 xushi-skills" in guide
    assert "Run an interactive delivery check" in guide
    assert "我刚刚发送了一条序时测试提醒" in guide
    assert "Common mistakes to avoid" in guide
    assert "action.executor_id" in guide
    assert "Restart `xushi-daemon`" in guide
    assert "Delivery is `delayed`" in guide
    assert "401 Unauthorized" in guide
    assert "xushi doctor" in guide
    assert "xushi deliveries" in guide


def test_install_scripts_use_safe_defaults() -> None:
    ps1 = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")
    sh = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")

    assert "$env:USERPROFILE" in ps1
    assert "XUSHI_BIN_DIR" in sh
    assert "releases/latest/download" in ps1
    assert "releases/latest/download" in sh
    assert "xushi-daemon" in ps1
    assert "xushi-daemon" in sh
    assert "Ensure-UserPath" in ps1
    assert "ensure_path_config" in sh
    assert "XUSHI_INSTALL_AGENT_PLUGINS" in ps1
    assert "XUSHI_INSTALL_AGENT_PLUGINS" in sh
    assert "XUSHI_OPENCLAW_PLUGINS_DIR" in ps1
    assert "XUSHI_OPENCLAW_PLUGINS_DIR" in sh
    assert "OPENCLAW_PLUGINS_DIR" in sh
    assert "XUSHI_INSTALL_AGENT_SKILLS" in ps1
    assert "XUSHI_INSTALL_AGENT_SKILLS" in sh
    assert "XUSHI_OPENCLAW_SKILLS_DIR" in ps1
    assert "XUSHI_OPENCLAW_SKILLS_DIR" in sh
    assert "XUSHI_HERMES_SKILLS_DIR" in ps1
    assert "XUSHI_HERMES_SKILLS_DIR" in sh
    assert "OPENCLAW_SKILLS_DIR" in ps1
    assert "OPENCLAW_SKILLS_DIR" in sh
    assert "HERMES_SKILLS_DIR" in ps1
    assert "HERMES_SKILLS_DIR" in sh
    assert "--openclaw-skills-dir" in sh
    assert "--hermes-skills-dir" in sh
    assert "openclaw" in ps1
    assert "hermes" in ps1
    assert "openclaw" in sh
    assert "hermes" in sh
    assert "CODEX_HOME" not in ps1
    assert "CODEX_HOME" not in sh
    assert "plugins install" in ps1
    assert "plugins install" in sh
    assert "skills install" in ps1
    assert "skills install" in sh
    assert "xushi-skills.zip" not in ps1
    assert "xushi-skills.zip" not in sh
    assert "xushi-openclaw-plugin.zip" not in ps1
    assert "xushi-openclaw-plugin.zip" not in sh


def test_openclaw_hooks_agent_uses_environment_configuration() -> None:
    bridge = (ROOT / "src" / "xushi" / "bridges.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "OPENCLAW_HOOKS_TOKEN" in bridge
    assert "/hooks/agent" in bridge
    assert "xushi-notify-" not in bridge
    assert "build_openclaw_hooks_agent_body" in bridge
    assert "mode\": \"hooks_agent\"" in readme
    assert "~/.xushi/config.json" in readme


def test_openclaw_plugin_does_not_mutate_executor_configuration() -> None:
    manifest = (ROOT / "plugins" / "openclaw-xushi" / "openclaw.plugin.json").read_text(
        encoding="utf-8"
    )
    source = (ROOT / "plugins" / "openclaw-xushi" / "src" / "index.ts").read_text(
        encoding="utf-8"
    )

    assert "xushi_list_executors" in manifest
    assert "xushi_reload_config" in manifest
    assert "xushi_reload_config" in source
    assert "xushi_list_runs" in manifest
    assert "xushi_confirm_latest_run" in manifest
    assert "xushi_save_executor" not in manifest
    assert "xushi_save_executor" not in source


def test_line_endings_are_controlled_for_cross_platform_scripts() -> None:
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "*.sh text eol=lf" in attributes
    assert "*.py text eol=lf" in attributes
    assert "*.yml text eol=lf" in attributes
    assert "*.md text eol=lf" in attributes


def test_release_workflow_publishes_tagged_artifacts() -> None:
    release_workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    build_workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")

    assert "tags: [\"v*\"]" in release_workflow
    assert "softprops/action-gh-release" in release_workflow
    assert "actions/upload-artifact" in release_workflow
    assert "actions/download-artifact" in release_workflow
    assert "scripts/prepare_release_assets.py" in release_workflow
    assert "--skills" not in release_workflow
    assert "--plugin" not in release_workflow
    assert "merge-multiple: true" in release_workflow
    assert "SHA256SUMS.txt" in release_workflow
    assert "generate_release_notes: true" in release_workflow
    assert "--skills" not in build_workflow
    assert "--plugin" not in build_workflow
    assert "xushi-skills.zip" not in release_workflow
    assert "xushi-skills.zip" not in build_workflow
    assert "xushi-openclaw-plugin.zip" not in release_workflow
    assert "xushi-openclaw-plugin.zip" not in build_workflow


def test_build_workflow_does_not_upload_pyinstaller_spec_files() -> None:
    build_workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")

    assert "*.spec" not in build_workflow


def test_build_workflow_runs_metadata_consistency_script() -> None:
    build_workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    script = ROOT / "scripts" / "check_project_metadata.py"

    assert script.exists()
    assert "scripts/check_project_metadata.py" in build_workflow


def test_github_community_health_files_exist() -> None:
    assert (ROOT / "CONTRIBUTING.md").exists()
    assert (ROOT / "SECURITY.md").exists()
    assert (ROOT / ".github" / "pull_request_template.md").exists()
    assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").exists()
    assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml").exists()


def test_contributing_documents_required_checks() -> None:
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

    assert "uv run pytest" in contributing
    assert "uv run ruff check ." in contributing
    assert "node --check plugins/openclaw-xushi/dist/index.js" in contributing


def test_security_policy_avoids_private_tokens_in_reports() -> None:
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")

    assert "不要公开粘贴 token" in security
    assert "GitHub Security Advisory" in security


def test_xushi_skills_include_agent_task_type_guidance() -> None:
    skill = (ROOT / "skills" / "xushi-skills" / "SKILL.md").read_text(encoding="utf-8")
    task_types = (
        ROOT / "skills" / "xushi-skills" / "references" / "task-types.md"
    ).read_text(encoding="utf-8")
    schema_patterns = (
        ROOT / "skills" / "xushi-skills" / "references" / "schema-patterns.md"
    ).read_text(encoding="utf-8")
    questions = (
        ROOT / "skills" / "xushi-skills" / "references" / "clarification-questions.md"
    ).read_text(encoding="utf-8")
    optimization_notes = (
        ROOT / "skills" / "xushi-skills" / "references" / "optimization-notes.md"
    ).read_text(encoding="utf-8")

    assert not (ROOT / "skills" / "xushi-skills" / "agents" / "openai.yaml").exists()
    assert "name: xushi-skills" in skill
    assert "OpenClaw/Hermes-priority" in skill
    assert "Prefer OpenClaw and Hermes integration paths" in skill
    assert "anchor: \"completion\"" in skill
    assert "confirming the latest pending run" in skill
    assert "喝水" in task_types
    assert "起立" in task_types
    assert "deadline" in task_types
    assert "floating" in task_types
    assert "requires_confirmation: true" in task_types
    assert "quiet_policy" in task_types
    assert "mode: \"bypass\"" in task_types
    assert "FREQ=HOURLY;INTERVAL=2" in schema_patterns
    assert "Global Quiet Policy" in schema_patterns
    assert '"behavior": "delay"' in schema_patterns
    assert "Common wrong pattern" in schema_patterns
    assert "下一次提醒要按固定时间算" in questions
    assert "确认完成" in questions
    assert "docs/xushi-feedback-notes.md" in optimization_notes
    assert "Do not upload" in optimization_notes


def test_bundled_xushi_skills_match_repository_copy() -> None:
    source_root = ROOT / "skills" / "xushi-skills"
    bundled_root = ROOT / "src" / "xushi" / "bundled_skills" / "xushi-skills"
    source_files = sorted(
        path.relative_to(source_root) for path in source_root.rglob("*") if path.is_file()
    )
    bundled_files = sorted(
        path.relative_to(bundled_root) for path in bundled_root.rglob("*") if path.is_file()
    )

    assert bundled_files == source_files
    for relative_path in source_files:
        assert (bundled_root / relative_path).read_text(encoding="utf-8") == (
            source_root / relative_path
        ).read_text(encoding="utf-8")


def test_openclaw_plugin_version_matches_app_and_bundled_copy() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    manifest = json.loads(
        (ROOT / "plugins" / "openclaw-xushi" / "openclaw.plugin.json").read_text(
            encoding="utf-8"
        )
    )
    package = json.loads(
        (ROOT / "plugins" / "openclaw-xushi" / "package.json").read_text(encoding="utf-8")
    )
    app_version = pyproject.split('version = "', maxsplit=1)[1].split('"', maxsplit=1)[0]

    assert manifest["version"] == app_version
    assert package["version"] == app_version


def test_bundled_openclaw_plugin_matches_repository_copy() -> None:
    source_root = ROOT / "plugins" / "openclaw-xushi"
    bundled_root = ROOT / "src" / "xushi" / "bundled_plugins" / "openclaw-xushi"
    source_files = sorted(
        path.relative_to(source_root) for path in source_root.rglob("*") if path.is_file()
    )
    bundled_files = sorted(
        path.relative_to(bundled_root) for path in bundled_root.rglob("*") if path.is_file()
    )

    assert bundled_files == source_files
    for relative_path in source_files:
        assert (bundled_root / relative_path).read_text(encoding="utf-8") == (
            source_root / relative_path
        ).read_text(encoding="utf-8")
