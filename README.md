<p align="center">
  <strong>序时 xushi</strong>
</p>

<p align="center">
  AI agent 优先的本地化日程管理与调度底座。
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

## 给人类看的

复制并粘贴以下提示词到你的 LLM Agent，例如 Claude Code、AmpCode、Cursor、OpenClaw：

```text
Install and configure xushi by following the instructions here:
https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/docs/guide/installation.md
```

Agent 会读取安装指南，检查你的系统环境，安装序时，初始化本地 token，并告诉你如何启动 `xushi-daemon`。

## 直接安装

如果你想自己执行安装脚本，可以先阅读脚本内容，再运行：

```powershell
irm https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.ps1 | iex
```

```bash
curl -fsSL https://raw.githubusercontent.com/Polaris-d/xushi/refs/heads/main/scripts/install.sh | sh
```

当前安装脚本会从 GitHub 克隆源码到 `~/.xushi/app`，使用 `uv` 安装依赖并执行 `xushi init`。后续发布 GitHub Release 后，脚本会优先下载预编译二进制。

## 为什么做序时

- Agent 原生：OpenClaw/Hermes 等工具只需要提交结构化 JSON，序时负责可靠调度。
- 本地优先：默认监听 `127.0.0.1`，使用本地 token，不依赖云端账号。
- 日常语义：支持固定时间、尽快、时间窗、截止、循环、完成确认、错过补偿和未完成跟进。
- Agent 投递：提醒任务可通过 `executor_id` 投递到 OpenClaw `/hooks/agent`；未配置 executor 时只走本地系统通知。
- 中国日历：内置中国大陆 2026 年节假日和调休数据，按节日名称分组。
- 可审计：每次触发生成 run 记录，支持 callback 更新长任务最终状态。
- 可分发：提供 wheel、PyInstaller 二进制构建脚本和 OpenClaw 插件骨架。

## 功能概览

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| Python daemon | 可用 | FastAPI + SQLite，本地调度与 API |
| CLI | 可用 | `init`、`doctor`、`create`、`list`、`trigger`、`tick`、`executors`、`notifications` |
| Web 管理台 | 可用 | 访问 daemon 根路径查看任务、运行记录和通知 |
| OpenClaw 插件 | 可用 | `plugins/openclaw-xushi`，提供创建、查询、触发、确认和 callback 工具 |
| 跟进闭环 | 可用 | 未确认任务按策略重复提醒，确认后停止 |
| 中国工作日 | 可用 | 节假日、调休、工作日顺延、节日名称查询 |
| 分发构建 | 可用 | wheel、PyInstaller、GitHub Actions |

## 本地开发

```powershell
uv sync
uv run xushi init --show-token
uv run xushi-daemon
```

访问：

- Web 管理台：`http://127.0.0.1:18766/`
- 健康检查：`http://127.0.0.1:18766/api/v1/health`

诊断本地配置和端口：

```powershell
uv run xushi doctor
```

可选环境变量：

- `XUSHI_CONFIG_PATH`：默认 `~/.xushi/config.json`
- `XUSHI_PORT`：默认 `18766`
- `XUSHI_SCHEDULER_INTERVAL_SECONDS`：默认 `30`
- `XUSHI_DATABASE_PATH`：默认 `~/.xushi/xushi.db`
- `XUSHI_API_TOKEN`：覆盖配置文件中的本地 token

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

OpenClaw executor 默认通过 OpenClaw 的 `/hooks/agent` 投递提醒，让 agent 处理消息并通过已配置的聊天 channel 送达用户。executor 不存入 SQLite，也不能通过 API 写入；请在 `~/.xushi/config.json` 的 `executors` 数组中配置，然后重启 `xushi-daemon` 生效。

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
        "to": "optional-recipient-id",
        "model": "openai/gpt-5.4-mini",
        "thinking": "low",
        "fallbacks": ["openai/gpt-5.4"],
        "deliver": true,
        "timeout_seconds": 120
      },
      "enabled": true
    }
  ]
}
```

可以用下面的命令查看 daemon 当前读到的 executor 配置：

```powershell
uv run xushi executors
```

`uv run xushi executor .\executor.openclaw.json` 只用于校验单个 executor 配置片段，不会写入数据库或运行态配置。OpenClaw 插件也只提供 `xushi_list_executors` 查看工具；配置写入由本地 `config.json` 管理。

OpenClaw `/hooks/agent` 可选字段均可在 executor config 中配置。序时使用 snake_case，发送给 OpenClaw 时转换为官方 camelCase：

| 序时配置 | OpenClaw 字段 | 说明 |
| --- | --- | --- |
| `name` | `name` | hook 显示名称 |
| `agent_id` | `agentId` | 指定处理提醒的 agent |
| `session_key` | `sessionKey` | 指定 agent 会话；OpenClaw 默认可能拒绝，需要启用 `hooks.allowRequestSessionKey` |
| `wake_mode` | `wakeMode` | `now` 或 `next-heartbeat` |
| `deliver` | `deliver` | 是否把 agent 回复发送到消息 channel |
| `channel` | `channel` | 例如 `last`、`telegram`、`slack` 或已配置插件 channel |
| `to` | `to` | 具体接收方 ID |
| `model` | `model` | 模型覆盖 |
| `thinking` | `thinking` | 推理强度覆盖 |
| `fallbacks` | `fallbacks` | 备用模型列表 |
| `timeout_seconds` | `timeoutSeconds` | agent run 超时时间 |

如果 OpenClaw Gateway 启用了 HTTPS 且使用自签名证书，才需要这样配置：

```json
{
  "webhook_url": "https://127.0.0.1:18789/hooks/agent",
  "insecure_tls": true
}
```

默认情况下建议使用 HTTP，或为 HTTPS 配置可信证书。`insecure_tls: true` 只适合本机自签名证书场景。

如果要固定由某个 agent 和飞书会话处理提醒，推荐在 OpenClaw hooks 配置里设置 `defaultSessionKey` 和 mapping，而不是从序时传 `session_key`：

```json
{
  "hooks": {
    "enabled": true,
    "token": "<different-from-gateway-token>",
    "defaultSessionKey": "agent:chase:feishu:...",
    "mappings": [
      {
        "match": {"path": "agent"},
        "action": "agent",
        "agentId": "chase",
        "sessionKey": "agent:chase:feishu:...",
        "deliver": true,
        "channel": "feishu"
      }
    ]
  }
}
```

`hooks.token` 请使用独立 token，不要复用 gateway auth token。

提醒要真正发给 agent，需要在任务 action 上引用执行器：

```json
{
  "type": "reminder",
  "executor_id": "openclaw",
  "payload": {
    "message": "该喝水了",
    "channel": "feishu"
  }
}
```

如果 `reminder` 没有 `executor_id`，序时只会尝试本地桌面通知；在无桌面的 Linux 服务器上通常只能留下 fallback 记录。

`webhook` 和 `hermes` executor 暂时只保留 schema 位置，v1 不执行投递。`command` executor 已移除，避免跨平台和安全边界变复杂。

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

## 分发构建

```powershell
uv build --wheel
uv run --with pyinstaller python scripts/build_binaries.py
```

仓库内置 `.github/workflows/build.yml`，会在 Windows、macOS、Linux 上运行测试、lint、wheel 构建和 PyInstaller 二进制构建，并上传构建产物。

## 贡献与安全

- 贡献指南：[CONTRIBUTING.md](CONTRIBUTING.md)
- 安全策略：[SECURITY.md](SECURITY.md)

## 许可证

本项目使用 [MIT License](LICENSE)。
