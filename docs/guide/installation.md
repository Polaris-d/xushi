# Installation

## 给人类看的

复制并粘贴以下提示词到你的 LLM Agent；如果你使用 OpenClaw 或 Hermes，优先从它们的集成环境里执行：

```text
Install and configure xushi by following the instructions here:
https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/docs/guide/installation.md
```

如果你想自己安装，可以直接运行对应平台脚本。

Windows PowerShell：

```powershell
irm https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.ps1 | iex
```

macOS / Linux：

```bash
curl -fsSL https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.sh | sh
```

## For LLM Agents

You are helping the user install and configure xushi, a local-first scheduler for AI agents.

### Step 0: Explain what will happen

Tell the user that xushi will be installed from GitHub Releases into `~/.xushi/bin`, configured as a global command, initialized with a local API token, and verified with `xushi doctor`. The daemon listens on `127.0.0.1` by default.

Also make the integration priority explicit: xushi prioritizes OpenClaw and Hermes. The normal path is installing xushi, then configuring the OpenClaw plugin and `/hooks/agent` executor or the Hermes agent webhook. Do not install skills unless the user agrees.

### Step 1: Check prerequisites

On Windows PowerShell, check that `Invoke-WebRequest` is available:

```powershell
Get-Command Invoke-WebRequest
```

On macOS / Linux, check that `curl` is available:

```bash
curl --version
```

No source checkout, `git`, or `uv` is required for a normal release install. `uv` is only needed for local development.

### Step 2: Run the installer

On Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.ps1 | iex
```

On macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.sh | sh
```

Optional environment variables:

| Variable | Purpose |
| --- | --- |
| `XUSHI_VERSION` | Release tag to install, for example `v0.1.5`; default is latest |
| `XUSHI_BIN_DIR` | Binary install directory; default is `~/.xushi/bin` |
| `XUSHI_REPO_SLUG` | GitHub repository slug; default is `Polaris-d/xushi` |
| `XUSHI_INSTALL_AGENT_SKILLS` | Optional comma-separated auxiliary skill targets; currently supports `openclaw` and `hermes` |
| `XUSHI_OPENCLAW_SKILLS_DIR` | Optional OpenClaw skills root override; if unset, the installer also honors `OPENCLAW_SKILLS_DIR`; default is `${OPENCLAW_HOME:-~/.openclaw}/skills` |
| `XUSHI_HERMES_SKILLS_DIR` | Optional Hermes skills root override; if unset, the installer also honors `HERMES_SKILLS_DIR`; default is `${HERMES_HOME:-~/.hermes}/skills` |

Do not install skills without the user's permission. Ask a short question before setting this option, for example: "是否同时为 OpenClaw/Hermes 安装 xushi-skills 任务类型指南？"

Use these targets:

- `openclaw`: installs into `${OPENCLAW_HOME:-~/.openclaw}/skills/xushi-skills`.
- `hermes`: installs into `${HERMES_HOME:-~/.hermes}/skills/xushi-skills`.

If the user's OpenClaw or Hermes skills directory has been customized, use `XUSHI_OPENCLAW_SKILLS_DIR` or `XUSHI_HERMES_SKILLS_DIR` before running the installer. If an agent environment already exposes `OPENCLAW_SKILLS_DIR` or `HERMES_SKILLS_DIR`, the installer will honor those too. The directory value should be the skills root, not the agent home; the installer creates or replaces the `xushi-skills` child folder inside it.

If the user agrees, install xushi and `xushi-skills` for OpenClaw/Hermes in one non-interactive command.

Windows PowerShell:

```powershell
$env:XUSHI_INSTALL_AGENT_SKILLS = "openclaw,hermes"
$env:XUSHI_OPENCLAW_SKILLS_DIR = "D:\Agents\OpenClaw\skills"
$env:XUSHI_HERMES_SKILLS_DIR = "D:\Agents\Hermes\skills"
irm https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.ps1 | iex
```

macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.sh | XUSHI_INSTALL_AGENT_SKILLS=openclaw,hermes sh
```

With custom skills directories:

```bash
curl -fsSL https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.sh | XUSHI_INSTALL_AGENT_SKILLS=openclaw,hermes XUSHI_OPENCLAW_SKILLS_DIR="$HOME/agents/openclaw-skills" XUSHI_HERMES_SKILLS_DIR="$HOME/agents/hermes-skills" sh
```

The shell installer also accepts explicit arguments, which can be easier for agents to compose safely:

```bash
curl -fsSL https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.sh | sh -s -- --agent-skills openclaw,hermes --openclaw-skills-dir "$HOME/agents/openclaw-skills" --hermes-skills-dir "$HOME/agents/hermes-skills"
```

### Step 3: Verify setup

Open a new shell after installation so the updated PATH is loaded, then run:

```bash
xushi doctor
```

The installer also runs `xushi init --show-token` and `xushi doctor` by absolute path immediately after downloading the binaries.

If `XUSHI_INSTALL_AGENT_SKILLS=openclaw,hermes` was provided, verify that `xushi-skills` exists under the configured OpenClaw and Hermes skills directories. When no override is set, check `${OPENCLAW_HOME:-~/.openclaw}/skills/xushi-skills` and `${HERMES_HOME:-~/.hermes}/skills/xushi-skills`.

### Step 4: Start daemon

Start the local daemon:

```bash
xushi-daemon
```

Then verify health:

```bash
curl http://127.0.0.1:18766/api/v1/health
```

On Windows PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:18766/api/v1/health
```

### Step 5: Configure agent integration

Read the token printed by `xushi init --show-token` or from the local config file. Set it as `XUSHI_API_TOKEN` in the agent environment and use:

```text
XUSHI_BASE_URL=http://127.0.0.1:18766
```

For OpenClaw, use the plugin in `plugins/openclaw-xushi` and configure `tokenEnv` as `XUSHI_API_TOKEN`.

If reminders should be delivered back into OpenClaw, enable OpenClaw hooks and configure an executor in `~/.xushi/config.json`. Prefer passing OpenClaw hook secrets through the daemon environment instead of storing them in xushi task or executor JSON:

```bash
export OPENCLAW_HOOKS_TOKEN="<local-openclaw-hooks-token>"
```

Then edit the `executors` array so the OpenClaw executor points directly at OpenClaw `/hooks/agent`. Restart `xushi-daemon` after editing the file.

```json
{
  "executors": [
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
  ]
}
```

For Hermes, configure a local HTTP agent webhook. The `message_field` option controls which field receives the generated prompt.

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

Reminder tasks must set `action.executor_id` to the configured executor id, such as `openclaw` or `hermes`.

Use `xushi executors` to confirm what the daemon loaded from `config.json`.

### Notes

- Do not commit the generated local config file.
- Do not paste the full local token into public issues, logs, or documentation.
- If port `18766` is occupied, set `XUSHI_PORT` before running `xushi-daemon`.
- If `xushi` is not found after install, open a new shell or add `~/.xushi/bin` to PATH manually.

### Manual upgrade

xushi does not silently auto-upgrade. Use the CLI upgrade flow:

```bash
xushi upgrade status
xushi upgrade apply --yes
```

For a specific release tag:

```bash
xushi upgrade apply --version v0.1.5 --yes
```

The upgrade command creates a backup of the local config and SQLite database before replacing global command binaries from GitHub Releases. If the upgrade fails or the user wants to restore data, run:

```bash
xushi upgrade rollback
```
