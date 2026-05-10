<h1 align="center">xushi</h1>

<p align="center">
  <img src="docs/assets/xushi-logo.png" alt="xushi logo" width="180">
</p>

<p align="center">
  A local-first scheduling and reminder runtime for AI agents.
</p>

<p align="center">
  <a href="README.md">中文</a>
  ·
  <a href="docs/guide/installation.md">Installation Guide</a>
  ·
  <a href="plugins/openclaw-xushi">OpenClaw Plugin</a>
</p>

<p align="center">
  <a href="https://github.com/Polaris-d/xushi/actions/workflows/build.yml">
    <img alt="build" src="https://img.shields.io/github/actions/workflow/status/Polaris-d/xushi/build.yml?branch=main">
  </a>
  <a href="https://github.com/Polaris-d/xushi/blob/main/LICENSE">
    <img alt="license" src="https://img.shields.io/badge/license-MIT-blue">
  </a>
  <img alt="python" src="https://img.shields.io/badge/python-3.12%2B-3776AB">
  <img alt="agent first" src="https://img.shields.io/badge/agent--first-local%20scheduler-111827">
</p>

xushi is a local daemon for schedules, reminders, compensation, follow-ups, and auditable run logs, with priority support for OpenClaw and Hermes. It also works with Claude Code, Cursor, and other agent tools through the same local API and executor model.

## Human-Friendly Install

Paste this prompt into your LLM agent. If you use OpenClaw or Hermes, prefer running it from that integration environment:

```text
Install and configure xushi by following the instructions here:
https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/docs/guide/installation.md
```

The agent will read the guide, check the local environment, download xushi from GitHub Releases, initialize a local token, and tell you how to start `xushi-daemon`. Before installation, the agent should ask whether to install `xushi-skills`; this is strongly recommended because it helps OpenClaw/Hermes understand task types, quiet policy, and confirmation flows. After configuration, the agent should send a test reminder and wait for you to confirm that the target channel received it.

## Direct Install

The installer downloads the current platform's `xushi` and `xushi-daemon` binaries from GitHub Releases, installs them into `~/.xushi/bin`, and configures `xushi` as a global command.

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.ps1 | iex
```

macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.sh | sh
```

xushi prioritizes OpenClaw and Hermes integration. After installing xushi, configure the `plugins/openclaw-xushi` plugin, the OpenClaw `/hooks/agent` executor, or the Hermes agent webhook so reminders can flow back into agents and chat channels.

Strongly recommended: before installation, ask the user whether to install the task-type guide. After the user agrees, set `XUSHI_INSTALL_AGENT_SKILLS=openclaw,hermes` for non-interactive installation. The script should not ask again while running. This installs the same `xushi-skills` package into the OpenClaw and Hermes skills directories:

```bash
curl -fsSL https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.sh | XUSHI_INSTALL_AGENT_SKILLS=openclaw,hermes sh
```

If your OpenClaw or Hermes skills directory is customized, set `XUSHI_OPENCLAW_SKILLS_DIR` / `XUSHI_HERMES_SKILLS_DIR` to the skills root. The installer also honors existing `OPENCLAW_SKILLS_DIR` / `HERMES_SKILLS_DIR` variables.

After installing xushi and configuring an executor, ask the agent to send a real test reminder and confirm with the user that the message arrived in OpenClaw, Hermes, or the target chat channel. `xushi doctor` proves the local config is readable; the test reminder proves the delivery path works.

## Why xushi

| Feature | Value |
| --- | --- |
| Agent-native | Agents submit structured JSON while xushi owns reliable scheduling |
| Local-first | Binds to `127.0.0.1` by default and uses a local API token |
| Daily semantics | Supports fixed time, ASAP, windows, deadlines, recurrence, confirmation, and follow-up |
| Delivery loop | Can deliver reminders to OpenClaw or Hermes through `executor_id` |
| China calendar | Includes 2026 mainland China holidays and adjusted workdays |
| Auditable | Every trigger creates a run record with filtered queries, latest-run confirmation, and callbacks |
| Distributable | Ships wheels, PyInstaller binaries, Release assets, and an OpenClaw plugin |

## Quick Start

After installation, open a new shell and run:

```powershell
xushi doctor
xushi-daemon
```

Then open:

- Web console: `http://127.0.0.1:18766/`
- Health check: `http://127.0.0.1:18766/api/v1/health`

Local development still uses `uv`:

```powershell
uv sync
uv run xushi init --show-token
uv run xushi-daemon
```

Completion-based habits should keep `anchor: "completion"`. Night-time behavior belongs to the delivery layer: configure a global `quiet_policy` with `behavior: "delay"` and digest aggregation, then let normal tasks inherit it. Use task-level `quiet_policy: {"mode": "bypass"}` only for explicit night reminders such as early flights.

## Agent Executors

Executors are local config, not runtime data. Put them in the `executors` array in `~/.xushi/config.json`, then restart `xushi-daemon`.

OpenClaw:

```json
{
  "id": "openclaw",
  "kind": "openclaw",
  "name": "OpenClaw",
  "config": {
    "mode": "hooks_agent",
    "webhook_url": "http://127.0.0.1:18789/hooks/agent",
    "token_env": "OPENCLAW_HOOKS_TOKEN",
    "agent_id": "reminder-agent",
    "wake_mode": "now",
    "channel": "feishu",
    "deliver": true,
    "timeout_seconds": 120
  },
  "enabled": true
}
```

Hermes:

```json
{
  "id": "hermes",
  "kind": "hermes",
  "name": "Hermes",
  "config": {
    "mode": "agent_webhook",
    "webhook_url": "http://127.0.0.1:18790/hooks/agent",
    "token_env": "HERMES_API_TOKEN",
    "message_field": "prompt",
    "agent_id": "planner-agent",
    "conversation_id": "optional-conversation-id",
    "channel": "feishu",
    "deliver": true,
    "request_timeout_seconds": 30
  },
  "enabled": true
}
```

Use environment variables for tokens. Do not store real secrets in task JSON, sample files, or commits.

Useful run APIs for agents:

```http
GET /api/v1/runs?task_id=<task_id>&active_only=true&limit=10
Authorization: Bearer <XUSHI_API_TOKEN>
```

```http
POST /api/v1/tasks/{task_id}/runs/confirm-latest
Authorization: Bearer <XUSHI_API_TOKEN>
```

## Release And Upgrade

Tagged releases publish Python packages, Windows/macOS/Linux single-file binaries, the OpenClaw plugin zip, checksums, and generated release notes.

xushi never upgrades silently. Run upgrades explicitly:

```powershell
xushi upgrade status
xushi upgrade check --version v0.1.5
xushi upgrade backup
xushi upgrade apply --version v0.1.5 --yes
xushi upgrade rollback
```

If `--version` is omitted, `upgrade apply` downloads the latest GitHub Release.

## Checks

```powershell
uv run pytest
uv run ruff check .
node --check plugins/openclaw-xushi/dist/index.js
uv build --wheel
```

## License

xushi is released under the [MIT License](LICENSE).
