<h1 align="center">序时 xushi</h1>

<p align="center">
  <img src="docs/assets/xushi-logo.png" alt="序时 xushi logo" width="180">
</p>

<p align="center">
  AI agent 优先的本地化日程管理与调度底座。
</p>

<p align="center">
  <a href="README.en.md">English</a>
  ·
  <a href="docs/guide/installation.md">安装指南</a>
  ·
  <a href="plugins/openclaw-xushi">OpenClaw 插件</a>
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

序时是给 OpenClaw、Hermes、Claude Code、Cursor 等 agent 工具使用的本地日程与排期底座。它把提醒、调度、补偿、跟进和运行日志放在本机 daemon 中，让 agent 不需要自己可靠常驻，也能创建结构化、可审计、可确认的日常任务。

> GitHub 仓库描述建议：AI agent 优先的本地日程与排期底座，提供本机 daemon、结构化任务、可靠提醒、补偿跟进、OpenClaw/Hermes 投递和可审计运行记录。

## 给人类看的

复制并粘贴以下提示词到你的 LLM Agent，例如 Claude Code、AmpCode、Cursor、OpenClaw：

```text
Install and configure xushi by following the instructions here:
https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/docs/guide/installation.md
```

Agent 会读取安装指南，检查你的系统环境，从 GitHub Release 下载序时，初始化本地 token，并告诉你如何启动 `xushi-daemon`。

## 直接安装

安装脚本会从 GitHub Release 下载当前平台的 `xushi` 与 `xushi-daemon` 预编译二进制，默认安装到 `~/.xushi/bin`，并把该目录加入用户 PATH，使 `xushi` 成为全局命令。

Windows PowerShell：

```powershell
irm https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.ps1 | iex
```

macOS / Linux：

```bash
curl -fsSL https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.sh | sh
```

安装指定版本：

```bash
curl -fsSL https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.sh | XUSHI_VERSION=v0.1.2 sh
```

如果 agent 已经征得用户同意，也可以同时静默安装 `xushi-skills` 到 Codex，帮助 agent 正确选择喝水、起立活动、截止任务等任务类型：

```bash
curl -fsSL https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.sh | XUSHI_INSTALL_AGENT_SKILLS=codex sh
```

Windows PowerShell：

```powershell
$env:XUSHI_INSTALL_AGENT_SKILLS = "codex"
irm https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.ps1 | iex
```

## 为什么做序时

| 特性 | 价值 |
| --- | --- |
| Agent 原生 | OpenClaw、Hermes 等工具只提交结构化 JSON，序时负责可靠调度 |
| 本地优先 | 默认监听 `127.0.0.1`，使用本地 token，不依赖云端账号 |
| 日常语义 | 支持固定时间、尽快、时间窗、截止、循环、完成确认和未完成跟进 |
| 投递闭环 | 可通过 `executor_id` 投递到 OpenClaw 或 Hermes；未配置时走本地系统通知 |
| 中国日历 | 内置中国大陆 2026 年节假日和调休数据 |
| 可审计 | 每次触发生成 run 记录，支持 callback 更新长任务最终状态 |
| 可分发 | 提供 wheel、PyInstaller 二进制、Release 资产和 OpenClaw 插件 |

## 功能概览

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| Python daemon | 可用 | FastAPI + SQLite，本地调度与 API |
| CLI | 可用 | `init`、`doctor`、`create`、`list`、`trigger`、`tick`、`executors`、`notifications`、`upgrade` |
| Web 管理台 | 可用 | 访问 daemon 根路径查看任务、运行记录和通知 |
| OpenClaw 插件 | 可用 | `plugins/openclaw-xushi`，提供创建、查询、触发、确认和 callback 工具 |
| xushi-skills | 可用 | `skills/xushi-skills`，帮助 agent 判断任务类型、生成 schema 并适当追问 |
| OpenClaw executor | 可用 | 投递到 OpenClaw `/hooks/agent` |
| Hermes executor | 可用 | 可配置 HTTP agent webhook |
| 跟进闭环 | 可用 | 未确认任务按策略重复提醒，确认后停止 |
| 中国工作日 | 可用 | 节假日、调休、工作日顺延、节日名称查询 |
| 分发构建 | 可用 | wheel、PyInstaller、GitHub Actions Release |

## 快速使用

安装完成后，新终端中可以直接使用全局命令：

```powershell
xushi doctor
xushi-daemon
```

访问：

- Web 管理台：`http://127.0.0.1:18766/`
- 健康检查：`http://127.0.0.1:18766/api/v1/health`

本地开发仍然使用 `uv`：

```powershell
uv sync
uv run xushi init --show-token
uv run xushi-daemon
```

可选环境变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `XUSHI_CONFIG_PATH` | `~/.xushi/config.json` | 配置文件路径 |
| `XUSHI_PORT` | `18766` | daemon 监听端口 |
| `XUSHI_SCHEDULER_INTERVAL_SECONDS` | `30` | 调度扫描间隔 |
| `XUSHI_DATABASE_PATH` | `~/.xushi/xushi.db` | SQLite 数据库路径 |
| `XUSHI_API_TOKEN` | 配置文件 token | 覆盖本地 API token |
| `XUSHI_BIN_DIR` | `~/.xushi/bin` | Release 二进制安装目录 |

## 示例任务

```json
{
  "title": "饭后吃药",
  "schedule": {
    "kind": "recurring",
    "run_at": "2026-05-09T12:30:00+08:00",
    "rrule": "FREQ=DAILY",
    "timezone": "Asia/Shanghai",
    "missed_policy": "catch_up_latest"
  },
  "action": {
    "type": "reminder",
    "payload": {
      "message": "饭后吃药"
    }
  },
  "follow_up_policy": {
    "requires_confirmation": true,
    "grace_period": "PT10M",
    "interval": "PT5M",
    "max_attempts": 3,
    "ask_reschedule_on_timeout": true
  }
}
```

## 配置 Agent Executor

Executor 不存入 SQLite，也不能通过 API 写入；请在 `~/.xushi/config.json` 的 `executors` 数组中配置，然后重启 `xushi-daemon` 生效。

### OpenClaw

OpenClaw executor 默认通过 OpenClaw 的 `/hooks/agent` 投递提醒，让 agent 处理消息并通过已配置的聊天 channel 送达用户。

```json
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
    "to": "optional-recipient-id",
    "model": "openai/gpt-5.4-mini",
    "thinking": "low",
    "fallbacks": ["openai/gpt-5.4"],
    "deliver": true,
    "timeout_seconds": 120
  },
  "enabled": true
}
```

### Hermes

Hermes executor 支持可配置 HTTP agent webhook。默认请求体会把序时提醒整理为 `prompt` 字段，并附带 `source` 与 `metadata`；如果 Hermes 入口使用 `message` 等字段名，可以通过 `message_field` 调整。

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

如果 Hermes 本地入口不需要鉴权，可以显式设置 `"token_required": false`。建议优先通过 `token_env` 读取环境变量，不要把真实 token 写进仓库或任务 JSON。

提醒要真正发给 agent，需要在任务 action 上引用执行器：

```json
{
  "type": "reminder",
  "executor_id": "hermes",
  "payload": {
    "message": "该喝水了",
    "channel": "feishu"
  }
}
```

查看 daemon 当前读到的 executor 配置：

```powershell
xushi executors
```

如果 `reminder` 没有 `executor_id`，序时只会尝试本地桌面通知；在无桌面的 Linux 服务器上通常只能留下 fallback 记录。

长任务完成后可回调：

```http
POST /api/v1/runs/{run_id}/callback
Authorization: Bearer <XUSHI_API_TOKEN>
Content-Type: application/json

{
  "status": "succeeded",
  "result": {
    "agent_run_id": "remote_123",
    "summary": "已完成"
  }
}
```

## 验证

```powershell
uv run pytest
uv run ruff check .
node --check plugins/openclaw-xushi/dist/index.js
uv build --wheel
```

## 分发与升级

发布正式版本时创建并推送 SemVer tag：

```powershell
git tag v0.1.2
git push origin v0.1.2
```

`.github/workflows/release.yml` 会在 tag 上执行跨平台质量检查，生成 Python wheel/sdist、Windows/macOS/Linux 单文件二进制、OpenClaw 插件 zip，并在 GitHub Release 中附带 `SHA256SUMS.txt` 校验和与自动 release notes。

序时不会静默自动升级。用户需要显式执行 CLI 命令，升级器会先备份本地配置和 SQLite 数据，再从 GitHub Release 下载并替换全局命令：

```powershell
xushi upgrade status
xushi upgrade check --version v0.1.2
xushi upgrade backup
xushi upgrade apply --version v0.1.2 --yes
xushi upgrade rollback
```

如果省略 `--version`，`upgrade apply` 会下载 latest release。

## 贡献与安全

- 贡献指南：[CONTRIBUTING.md](CONTRIBUTING.md)
- 安全策略：[SECURITY.md](SECURITY.md)

## 许可证

本项目使用 [MIT License](LICENSE)。
