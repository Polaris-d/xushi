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

序时是优先适配 OpenClaw 和 Hermes 的本地日程与排期底座，也兼容 Claude Code、Cursor 等 agent 工具。它把提醒、调度、补偿、跟进和运行日志放在本机 daemon 中，让 agent 不需要自己可靠常驻，也能创建结构化、可审计、可确认的日常任务。

> GitHub 仓库描述建议：AI agent 优先的本地日程与排期底座，提供本机 daemon、结构化任务、可靠提醒、补偿跟进、OpenClaw/Hermes 投递和可审计运行记录。

## 给人类看的

复制并粘贴以下提示词到你的 LLM Agent；如果你使用 OpenClaw 或 Hermes，优先从它们的集成环境里执行：

```text
Install and configure xushi by following the instructions here:
https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/docs/guide/installation.md
```

Agent 会读取安装指南，检查你的系统环境，从 GitHub Release 下载序时，初始化本地 token，并告诉你如何启动 `xushi-daemon`。安装前 agent 应询问你是否同时安装 `xushi-skills`；这项强烈推荐开启，因为它能帮助 OpenClaw/Hermes 更准确地理解任务类型、免打扰策略和确认流程。配置完成后，agent 还应发送一条测试提醒，并等待你确认目标渠道确实收到了消息。

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
curl -fsSL https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.sh | XUSHI_VERSION=v0.1.9 sh
```

序时优先适配 OpenClaw 和 Hermes。安装后建议优先配置 `plugins/openclaw-xushi` 插件、OpenClaw `/hooks/agent` executor，或 Hermes agent webhook，把提醒投递回 agent 和聊天渠道。

强烈推荐：安装前请先询问用户是否同时安装 OpenClaw 插件和任务类型指南。得到用户同意后，可以设置 `XUSHI_INSTALL_AGENT_PLUGINS=openclaw` 与 `XUSHI_INSTALL_AGENT_SKILLS=openclaw,hermes` 静默安装，不要在脚本执行中再次追问。安装脚本会调用当前版本的 `xushi plugins install` / `xushi skills install`，把随应用内置的 OpenClaw 插件和 `xushi-skills` 安装到对应目录，避免插件、skills 与程序版本错配：

```bash
curl -fsSL https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.sh | XUSHI_INSTALL_AGENT_PLUGINS=openclaw XUSHI_INSTALL_AGENT_SKILLS=openclaw,hermes sh
```

如果你的 OpenClaw 或 Hermes skills 目录做过调整，可以设置 `XUSHI_OPENCLAW_SKILLS_DIR` / `XUSHI_HERMES_SKILLS_DIR` 指定 skills 根目录；安装器也会兼容已有的 `OPENCLAW_SKILLS_DIR` / `HERMES_SKILLS_DIR`。

Windows PowerShell：

```powershell
$env:XUSHI_INSTALL_AGENT_SKILLS = "openclaw,hermes"
$env:XUSHI_INSTALL_AGENT_PLUGINS = "openclaw"
irm https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.ps1 | iex
```

安装与 executor 配置完成后，请让 agent 发一条真实测试提醒，并让用户确认是否已在 OpenClaw、Hermes 或目标聊天渠道收到消息。`xushi doctor` 只证明本地配置可读，测试提醒才证明投递链路真的通了。

## 为什么做序时

| 特性 | 价值 |
| --- | --- |
| Agent 原生 | OpenClaw、Hermes 等工具只提交结构化 JSON，序时负责可靠调度 |
| 本地优先 | 默认监听 `127.0.0.1`，使用本地 token，不依赖云端账号 |
| 日常语义 | 支持固定时间、尽快、时间窗、截止、循环、完成确认和未完成跟进 |
| 投递闭环 | 可通过 `executor_id` 投递到 OpenClaw 或 Hermes；未配置时走本地系统通知 |
| 中国日历 | 内置中国大陆 2026 年节假日和调休数据 |
| 可审计 | 每次触发生成 run 记录，支持过滤查询、最近确认和 callback 更新长任务最终状态 |
| 可分发 | 提供 wheel、PyInstaller 二进制、Release 资产和 OpenClaw 插件 |

## 功能概览

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| Python daemon | 可用 | FastAPI + SQLite，本地调度与 API |
| CLI | 可用 | `init`、`doctor`、`create`、`list`、`trigger`、`runs`、`confirm-latest`、`tick`、`executors`、`reload-config`、`notifications`、`deliveries`、`retry-deliveries`、`plugins`、`skills`、`upgrade` |
| Web 管理台 | 可用 | 访问 daemon 根路径查看任务、运行记录和通知 |
| OpenClaw 插件 | 可用 | `plugins/openclaw-xushi`，提供创建、查询、触发、运行记录过滤、失败投递重试、最近确认和 callback 工具 |
| xushi-skills | 可用 | `skills/xushi-skills`，帮助 agent 判断任务类型、生成 schema、适当追问并记录本地优化反馈草稿 |
| OpenClaw executor | 可用 | 投递到 OpenClaw `/hooks/agent` |
| Hermes executor | 可用 | 可配置 HTTP agent webhook |
| 跟进闭环 | 可用 | 未确认任务按策略重复提醒，确认后取消同源待处理跟进 |
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
| `XUSHI_SQLITE_JOURNAL_MODE` | `delete` | SQLite journal 模式，可选 `wal` 提升并发读写 |
| `XUSHI_SQLITE_SYNCHRONOUS` | `full` | SQLite 同步策略，可选 `normal` 或 `off` |
| `XUSHI_AUTO_RETRY_FAILED_DELIVERIES` | `false` | 是否自动重试失败 delivery，默认关闭 |
| `XUSHI_AUTO_RETRY_MAX_ATTEMPTS` | `1` | 每条失败链最多自动重试次数 |
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

健康习惯更适合用完成时间重新计时；夜间不打扰应配置为全局免打扰策略，而不是改掉任务语义：

```json
{
  "quiet_policy": {
    "enabled": true,
    "timezone": "Asia/Shanghai",
    "windows": [
      {"start": "12:30", "end": "14:00", "days": "workdays"},
      {"start": "22:30", "end": "08:00", "days": "everyday"}
    ],
    "behavior": "delay",
    "aggregation": {"enabled": true, "mode": "digest", "max_items": 10}
  }
}
```

任务本身继续表达“完成后重新计时”：

```json
{
  "title": "喝水",
  "schedule": {
    "kind": "recurring",
    "run_at": "2026-05-10T09:00:00+08:00",
    "rrule": "FREQ=HOURLY;INTERVAL=2",
    "timezone": "Asia/Shanghai",
    "anchor": "completion",
    "missed_policy": "catch_up_latest"
  },
  "action": {
    "type": "reminder",
    "payload": {
      "message": "该喝水了"
    }
  },
  "follow_up_policy": {
    "requires_confirmation": true,
    "grace_period": "PT10M",
    "interval": "PT10M",
    "max_attempts": 3
  }
}
```

如果某个任务必须在免打扰时段提醒，例如凌晨赶飞机，可以在任务上设置 `quiet_policy: {"mode": "bypass"}`。

## 配置 Agent Executor

Executor 不存入 SQLite，也不能通过 API 写入；请在 `~/.xushi/config.json` 的 `executors` 数组中配置。修改 `executors`、全局 `quiet_policy` 或自动重试策略后，调用 `xushi reload-config`、OpenClaw 工具 `xushi_reload_config`，或 `POST /api/v1/config/reload` 即可让运行中的 daemon 重新加载。修改 API token、数据库路径、SQLite PRAGMA、监听地址、端口、调度间隔或 daemon 进程环境变量时仍需重启 `xushi-daemon`。

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

这里有两个容易混淆的 token：OpenClaw 插件调用序时 API 时使用 `XUSHI_API_TOKEN`；序时 daemon 调用 OpenClaw hooks 时使用 `OPENCLAW_HOOKS_TOKEN`，并且这个变量必须存在于 `xushi-daemon` 进程环境中。OpenClaw Gateway 如果启用了 HTTPS，`webhook_url` 也必须改成 `https://...`；本机自签名证书场景可显式设置 `"insecure_tls": true`。如果不设置 `agent_id`，OpenClaw 可能路由到默认 agent/session。

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

重新加载配置并查看当前 executor 配置：

```powershell
xushi reload-config
xushi executors
xushi doctor
```

如果 `reminder` 没有 `executor_id`，序时只会尝试本地桌面通知；在无桌面的 Linux 服务器上通常只能留下 fallback 记录。

修复 executor token、URL、TLS 或 agent 路由配置后，先 reload config；如果改的是 daemon 环境变量或启动级配置则重启 daemon。然后可以重试仍需要投递的失败记录：

```powershell
xushi reload-config
xushi retry-deliveries
```

也可以在配置中打开 `auto_retry_failed_deliveries`，让 daemon 在 tick 中按 `auto_retry_max_attempts` 自动创建有限次数 retry；默认关闭，避免配置错误时反复打扰外部系统。

长任务完成后可回调：

```http
GET /api/v1/runs?task_id=<task_id>&active_only=true&limit=10
Authorization: Bearer <XUSHI_API_TOKEN>
```

运行期指标可通过本地 API 查看，包含投递成功/失败、自动重试和最近 tick 摘要；列表 API 默认返回 100 条，可显式传 `limit` 调整：

```http
GET /api/v1/metrics
Authorization: Bearer <XUSHI_API_TOKEN>
```

当用户已经说明某个任务完成，且 agent 已知道 `task_id` 时，可以直接确认该任务最近一次待确认主运行记录：

```http
POST /api/v1/tasks/{task_id}/runs/confirm-latest
Authorization: Bearer <XUSHI_API_TOKEN>
```

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
git tag v0.1.9
git push origin v0.1.9
```

`.github/workflows/release.yml` 会在 tag 上执行跨平台质量检查，生成 Python wheel/sdist、Windows/macOS/Linux 单文件二进制，并在 GitHub Release 中附带 `SHA256SUMS.txt` 校验和与自动 release notes。OpenClaw 插件随 `xushi` 应用内置安装，也可以另行发布到 ClawHub；GitHub Release 不再提供独立插件 zip。

序时不会静默自动升级。用户需要显式执行 CLI 命令，升级器会先备份本地配置和 SQLite 数据，再从 GitHub Release 下载并替换全局命令：

```powershell
xushi upgrade status
xushi upgrade check --version v0.1.9
xushi upgrade backup
xushi upgrade apply --version v0.1.9 --yes
xushi upgrade rollback
```

如果省略 `--version`，`upgrade apply` 会下载 latest release。

如果之前安装过 `xushi-skills`，升级后请用新版本程序同步一次内置 skills：

```powershell
xushi plugins status openclaw
xushi plugins install openclaw
xushi skills status
xushi skills install --targets openclaw,hermes
```

## 贡献与安全

- 贡献指南：[CONTRIBUTING.md](CONTRIBUTING.md)
- 安全策略：[SECURITY.md](SECURITY.md)

## 许可证

本项目使用 [MIT License](LICENSE)。
