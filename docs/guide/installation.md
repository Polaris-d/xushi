# Installation

## 给人类看的

复制并粘贴以下提示词到你的 LLM Agent，例如 Claude Code、AmpCode、Cursor、OpenClaw：

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
| `XUSHI_VERSION` | Release tag to install, for example `v0.1.0`; default is latest |
| `XUSHI_BIN_DIR` | Binary install directory; default is `~/.xushi/bin` |
| `XUSHI_REPO_SLUG` | GitHub repository slug; default is `Polaris-d/xushi` |

### Step 3: Verify setup

Open a new shell after installation so the updated PATH is loaded, then run:

```bash
xushi doctor
```

The installer also runs `xushi init --show-token` and `xushi doctor` by absolute path immediately after downloading the binaries.

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
xushi upgrade apply --version v0.1.1 --yes
```

The upgrade command creates a backup of the local config and SQLite database before replacing global command binaries from GitHub Releases. If the upgrade fails or the user wants to restore data, run:

```bash
xushi upgrade rollback
```
