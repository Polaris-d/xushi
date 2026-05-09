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

Tell the user that xushi will be installed into `~/.xushi/app`, initialized with a local API token, and verified with `xushi doctor`. The daemon listens on `127.0.0.1` by default.

### Step 1: Check prerequisites

Check that `git` and `uv` are available.

```bash
git --version
uv --version
```

If `uv` is missing, ask the user to install it from the official documentation:

```text
https://docs.astral.sh/uv/getting-started/installation/
```

### Step 2: Run the installer

On Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.ps1 | iex
```

On macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.sh | sh
```

### Step 3: Verify setup

After installation, run:

```bash
cd ~/.xushi/app
uv run xushi doctor
```

On Windows PowerShell:

```powershell
Set-Location "$env:USERPROFILE\.xushi\app"
uv run xushi doctor
```

### Step 4: Start daemon

Start the local daemon:

```bash
uv run xushi-daemon
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

Then edit the `executors` array so the OpenClaw executor points directly at OpenClaw `/hooks/agent`. This path lets OpenClaw run an agent turn and deliver the reply through the configured chat channel, such as Feishu. Restart `xushi-daemon` after editing the file.

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
        "name": "Xushi",
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

Reminder tasks must set `action.executor_id` to `openclaw`.

Use `xushi executors` to confirm what the daemon loaded from `config.json`.

Optional OpenClaw `/hooks/agent` fields can also be configured in snake_case: `agent_id`, `wake_mode`, `channel`, `to`, `model`, `fallbacks`, `thinking`, and `timeout_seconds`.

If OpenClaw Gateway uses HTTPS with a self-signed local certificate, set:

```json
{
  "webhook_url": "https://127.0.0.1:18789/hooks/agent",
  "insecure_tls": true
}
```

Use `insecure_tls` only for local self-signed certificates. For normal HTTP, omit it. For HTTPS in shared environments, prefer a trusted certificate.

If the user wants a specific OpenClaw agent and Feishu session, configure `defaultSessionKey` and a hooks mapping on the OpenClaw side. Do not pass `session_key` from xushi unless OpenClaw explicitly allows request-provided session keys. The hooks token must be different from the gateway auth token.

### Notes

- Do not commit the generated local config file.
- Do not paste the full local token into public issues, logs, or documentation.
- If port `18766` is occupied, set `XUSHI_PORT` before running `xushi-daemon`.
