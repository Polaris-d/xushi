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

Also make the integration priority explicit: xushi prioritizes OpenClaw and Hermes. The normal path is installing xushi, then configuring the OpenClaw plugin and `/hooks/agent` executor or the Hermes agent webhook.

Before running the installer, ask the user whether to install the OpenClaw plugin and `xushi-skills`. This is strongly recommended for agent users because the plugin exposes xushi tools inside OpenClaw, and the skills teach agents how to choose task types, ask clarification questions, configure quiet policy, and record useful feedback. Do not install plugin or skills unless the user agrees; after consent, use the non-interactive installer parameters instead of asking again during installation.

Suggested wording:

```text
是否同时安装 OpenClaw 插件和 xushi-skills？强烈推荐安装。插件会把序时工具接入 OpenClaw，skills 会帮助 OpenClaw/Hermes 更准确地理解序时的任务类型、免打扰策略和确认流程。安装脚本可以通过参数静默完成，不会在安装过程中再次打断你。
```

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
| `XUSHI_INSTALL_AGENT_PLUGINS` | Optional comma-separated auxiliary plugin targets; currently supports `openclaw` |
| `XUSHI_INSTALL_AGENT_SKILLS` | Optional comma-separated auxiliary skill targets; currently supports `openclaw` and `hermes` |
| `XUSHI_OPENCLAW_PLUGINS_DIR` | Optional OpenClaw plugins root override; if unset, the installer also honors `OPENCLAW_PLUGINS_DIR`; default is `${OPENCLAW_HOME:-~/.openclaw}/plugins` |
| `XUSHI_OPENCLAW_SKILLS_DIR` | Optional OpenClaw skills root override; if unset, the installer also honors `OPENCLAW_SKILLS_DIR`; default is `${OPENCLAW_HOME:-~/.openclaw}/skills` |
| `XUSHI_HERMES_SKILLS_DIR` | Optional Hermes skills root override; if unset, the installer also honors `HERMES_SKILLS_DIR`; default is `${HERMES_HOME:-~/.hermes}/skills` |

Do not install plugin or skills without the user's permission. Ask before setting these options, and make the recommendation explicit. If the user agrees, set `XUSHI_INSTALL_AGENT_PLUGINS=openclaw` and `XUSHI_INSTALL_AGENT_SKILLS=openclaw,hermes`, or pass `--agent-plugins openclaw --agent-skills openclaw,hermes`; if the user declines, continue installing xushi itself without agent add-ons. The installer does not download standalone plugin or skills archives. It installs the OpenClaw plugin and `xushi-skills` bundled inside the current `xushi` app, so the plugin and skills versions follow the app version.

Use these targets:

- plugin target `openclaw`: installs into `${OPENCLAW_HOME:-~/.openclaw}/plugins/openclaw-xushi`.
- `openclaw`: installs into `${OPENCLAW_HOME:-~/.openclaw}/skills/xushi-skills`.
- `hermes`: installs into `${HERMES_HOME:-~/.hermes}/skills/xushi-skills`.

If the user's OpenClaw plugin or skills directory has been customized, use `XUSHI_OPENCLAW_PLUGINS_DIR`, `XUSHI_OPENCLAW_SKILLS_DIR`, or `XUSHI_HERMES_SKILLS_DIR` before running the installer. If an agent environment already exposes `OPENCLAW_PLUGINS_DIR`, `OPENCLAW_SKILLS_DIR`, or `HERMES_SKILLS_DIR`, the installer will honor those too. The directory value should be the plugins/skills root, not the agent home; the installer creates or replaces the `openclaw-xushi` or `xushi-skills` child folder inside it.

If the user agrees, install xushi and `xushi-skills` for OpenClaw/Hermes in one non-interactive command.

Windows PowerShell:

```powershell
$env:XUSHI_INSTALL_AGENT_SKILLS = "openclaw,hermes"
$env:XUSHI_INSTALL_AGENT_PLUGINS = "openclaw"
$env:XUSHI_OPENCLAW_PLUGINS_DIR = "D:\Agents\OpenClaw\plugins"
$env:XUSHI_OPENCLAW_SKILLS_DIR = "D:\Agents\OpenClaw\skills"
$env:XUSHI_HERMES_SKILLS_DIR = "D:\Agents\Hermes\skills"
irm https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.ps1 | iex
```

macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.sh | XUSHI_INSTALL_AGENT_PLUGINS=openclaw XUSHI_INSTALL_AGENT_SKILLS=openclaw,hermes sh
```

With custom skills directories:

```bash
curl -fsSL https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.sh | XUSHI_INSTALL_AGENT_PLUGINS=openclaw XUSHI_INSTALL_AGENT_SKILLS=openclaw,hermes XUSHI_OPENCLAW_PLUGINS_DIR="$HOME/agents/openclaw-plugins" XUSHI_OPENCLAW_SKILLS_DIR="$HOME/agents/openclaw-skills" XUSHI_HERMES_SKILLS_DIR="$HOME/agents/hermes-skills" sh
```

The shell installer also accepts explicit arguments, which can be easier for agents to compose safely:

```bash
curl -fsSL https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.sh | sh -s -- --agent-plugins openclaw --agent-skills openclaw,hermes --openclaw-plugins-dir "$HOME/agents/openclaw-plugins" --openclaw-skills-dir "$HOME/agents/openclaw-skills" --hermes-skills-dir "$HOME/agents/hermes-skills"
```

### Step 3: Verify setup

Open a new shell after installation so the updated PATH is loaded, then run:

```bash
xushi doctor
```

The installer also runs `xushi init --show-token` and `xushi doctor` by absolute path immediately after downloading the binaries.

If `XUSHI_INSTALL_AGENT_PLUGINS=openclaw` was provided, verify that `openclaw-xushi` exists under the configured OpenClaw plugins directory. If `XUSHI_INSTALL_AGENT_SKILLS=openclaw,hermes` was provided, verify that `xushi-skills` exists under the configured OpenClaw and Hermes skills directories. When no override is set, check `${OPENCLAW_HOME:-~/.openclaw}/plugins/openclaw-xushi`, `${OPENCLAW_HOME:-~/.openclaw}/skills/xushi-skills`, and `${HERMES_HOME:-~/.hermes}/skills/xushi-skills`. You can also run:

```bash
xushi plugins status openclaw
xushi skills status
```

The reported installed plugin and skills versions should match the current xushi app version.

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

Do this slowly and verify each boundary. Most failed installations are not caused by the xushi binary; they are caused by token scope, daemon restart, wrong executor ids, or hook URLs that are reachable from the user shell but not from the daemon process.

#### 5.1 Capture the local xushi connection

Run:

```bash
xushi doctor
```

Use the reported base URL and local token:

```text
XUSHI_BASE_URL=http://127.0.0.1:18766
XUSHI_API_TOKEN=<token from ~/.xushi/config.json or xushi init --show-token>
```

Common mistakes to avoid:

- Do not paste the full token into public logs, issues, or chat transcripts.
- If `xushi init --force` or a reinstall changed the token, update the agent/plugin environment too.
- `401 Unauthorized` usually means the agent process cannot see `XUSHI_API_TOKEN`, or it is using an old token.
- If the agent runs in a container, VM, or remote workspace, `127.0.0.1` may refer to the agent environment, not the user's machine. In that case, use a reachable local network address only if the user explicitly accepts the security tradeoff.

#### 5.2 Configure the agent-side client

For OpenClaw, install or enable the OpenClaw plugin with `xushi plugins install openclaw`, set its base URL to `XUSHI_BASE_URL`, and configure `tokenEnv` as `XUSHI_API_TOKEN`.

Pay attention to where environment variables live:

| Variable | Must be visible to | Purpose |
| ---- | ---- | ---- |
| `XUSHI_API_TOKEN` | OpenClaw plugin, Hermes client, or any agent process that calls xushi HTTP API | Authorizes agent -> `xushi-daemon` API calls |
| `OPENCLAW_HOOKS_TOKEN` | The `xushi-daemon` process | Authorizes `xushi-daemon` -> OpenClaw `/hooks/agent` delivery |
| `HERMES_API_TOKEN` | The `xushi-daemon` process | Authorizes `xushi-daemon` -> Hermes agent webhook delivery |

Common mistakes:

- `XUSHI_API_TOKEN` and `OPENCLAW_HOOKS_TOKEN` are different tokens for opposite directions. Do not reuse one as the other unless the target system explicitly says so.
- Setting a variable in a temporary terminal is not enough if the agent app or daemon was already running.
- After changing agent environment variables, restart or reload that agent integration before testing.
- After changing daemon environment variables, restart `xushi-daemon` from an environment that contains those variables.

#### 5.3 Configure one delivery executor first

Pick one target first, usually OpenClaw. Do not configure OpenClaw, Hermes, and webhook delivery all at once before one smoke test works.

Reminder tasks only use an agent delivery path when `action.executor_id` exactly matches an enabled executor id from `xushi executors`. If the field is missing or misspelled, the reminder falls back to local system notification instead of OpenClaw/Hermes.

#### 5.4 OpenClaw executor checklist

If reminders should be delivered back into OpenClaw, enable OpenClaw hooks and configure an executor in `~/.xushi/config.json`. Prefer passing OpenClaw hook secrets through the daemon environment instead of storing them in xushi task or executor JSON:

```bash
export OPENCLAW_HOOKS_TOKEN="<local-openclaw-hooks-token>"
```

On Windows PowerShell:

```powershell
$env:OPENCLAW_HOOKS_TOKEN = "<local-openclaw-hooks-token>"
xushi-daemon
```

Then edit the `executors` array so the OpenClaw executor points directly at OpenClaw `/hooks/agent`:

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

Check these details before testing:

- `token_env` is the environment variable name, not the secret value.
- `OPENCLAW_HOOKS_TOKEN` must be present in the `xushi-daemon` process environment.
- `webhook_url` must be reachable from the machine/process running `xushi-daemon`.
- If OpenClaw Gateway enables TLS, `webhook_url` must use `https://`. HTTP sent to an HTTPS port can show up as `BadStatusLine` or a protocol-looking delivery failure.
- If OpenClaw uses local HTTPS with a self-signed certificate, set `"insecure_tls": true` only for local/trusted setups after the user understands the tradeoff.
- Keep `deliver: true` when the expected result is a chat/channel message.
- Set `agent_id` when reminders must go to the current working agent rather than OpenClaw's default agent/session. Set `channel`, `to`, and `wake_mode` to match the user's real OpenClaw setup, not just the example.

Local self-signed HTTPS example:

```json
{
  "webhook_url": "https://127.0.0.1:18789/hooks/agent",
  "token_env": "OPENCLAW_HOOKS_TOKEN",
  "agent_id": "chase",
  "insecure_tls": true
}
```

#### 5.5 Hermes executor checklist

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

Check these details before testing:

- `message_field` must match the field Hermes expects, commonly `prompt` or `message`.
- `HERMES_API_TOKEN` must be present in the `xushi-daemon` process environment.
- `conversation_id`, `channel`, and `deliver` must match how Hermes routes messages to the user.
- If Hermes accepts the HTTP request but the user sees nothing, inspect Hermes routing/channel settings before changing xushi task schema.

#### 5.6 Restart and verify what xushi actually loaded

Restart `xushi-daemon` after editing `~/.xushi/config.json` or changing hook-token environment variables. Then run:

```bash
xushi doctor
xushi executors
```

Expected result:

- The chosen executor id, such as `openclaw` or `hermes`, appears in the output.
- `enabled` is `true`.
- The executor kind and mode match the intended target.
- `xushi doctor` does not report missing `token_env`, missing hook-token environment variables, or a missing OpenClaw `agent_id` for the route you intend to use.

If the output still shows old values, the daemon probably read a different config file or was not restarted. Re-check `xushi doctor` for `config_path` and restart the daemon from the same environment that contains the hook token variables.

### Step 6: Run an interactive delivery check

Configuration is not complete until the user confirms that a real test message can be delivered through the same path they will use in daily life.

#### 6.1 Confirm daemon and plugin connectivity

If OpenClaw plugin tools are available, call `xushi_health` first. If using raw HTTP, call:

```bash
curl http://127.0.0.1:18766/api/v1/health
```

If health fails, fix daemon startup, host, port, or network reachability before creating any task.

#### 6.2 Send one smoke-test reminder

Create a unique ASAP reminder and set `action.executor_id` to the executor being tested. Do not omit this field when testing OpenClaw/Hermes delivery.

With OpenClaw plugin tools, call `xushi_create_task` with this shape:

```json
{
  "title": "序时投递测试",
  "schedule": {
    "kind": "asap",
    "timezone": "Asia/Shanghai"
  },
  "action": {
    "type": "reminder",
    "executor_id": "openclaw",
    "payload": {
      "message": "这是一条序时安装后的投递测试。如果你看到它，请告诉 agent 已收到。"
    }
  },
  "follow_up_policy": {
    "requires_confirmation": false
  },
  "tags": ["setup-smoke-test"],
  "created_by": "agent"
}
```

For Hermes, change only `action.executor_id` to the Hermes executor id, usually `hermes`.

If no agent executor is configured yet, omit `executor_id` and verify that the local notification or Web console entry appears.

#### 6.3 Ask the user to confirm receipt

Ask exactly one clear question:

```text
我刚刚发送了一条序时测试提醒。你是否已经在目标渠道收到这条消息？
```

Only call the installation successful after the user confirms receipt.

#### 6.4 Debug by layer when the user did not receive it

Run:

```bash
xushi doctor
xushi executors
xushi runs --active-only --limit 10
xushi deliveries
xushi notifications
```

Read the result by layer:

- `xushi doctor` fails: local config, database path, token, or port is wrong.
- `xushi_health` or HTTP health fails from the agent: the agent cannot reach the daemon.
- Task is created but `xushi executors` does not show the expected executor: config file path is wrong or daemon was not restarted.
- Delivery is `delayed`: quiet policy is working; check `deliver_at` in `xushi deliveries`.
- Delivery is `failed`: inspect the delivery error and executor hook token/URL.
- Delivery error contains `missing token or token_env`: set the hook token in the `xushi-daemon` environment, not only in the agent/plugin environment.
- Delivery error looks like `BadStatusLine` or protocol noise: check whether OpenClaw is using HTTPS while the executor URL still starts with `http://`.
- Notification appears but the user saw no chat message: the OpenClaw/Hermes hook may have accepted the request but failed to route it to the configured channel.
- Local notification appears instead of OpenClaw/Hermes: `action.executor_id` was missing or did not exactly match an enabled executor id.
- Repeated smoke tests reuse an old task: add a unique title or `idempotency_key` for each setup attempt.

Fix the failing layer, restart `xushi-daemon` if config or environment changed, then retry the failed delivery or send one new smoke-test reminder:

```bash
xushi retry-deliveries
```

If the OpenClaw plugin is available, use `xushi_retry_deliveries` instead of shelling out. Do not mark setup complete until the user confirms receipt.

### Notes

- Do not commit the generated local config file.
- Do not paste the full local token into public issues, logs, or documentation.
- If port `18766` is occupied, set `XUSHI_PORT` before running `xushi-daemon`.
- If `xushi` is not found after install, open a new shell or add `~/.xushi/bin` to PATH manually.
- If a release binary is not available for the user's platform, use the wheel from the same GitHub Release as a fallback, for example `uv tool install xushi-<version>-py3-none-any.whl` or `pipx install xushi-<version>-py3-none-any.whl`.

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

If `xushi-skills` was installed before, sync it after upgrading so the installed skills match the current application version:

```bash
xushi plugins status openclaw
xushi plugins install openclaw
xushi skills status
xushi skills install --targets openclaw,hermes
```
