# 序时 xushi

序时是 AI agent 优先的本地化日程管理与调度底座。它用独立 daemon 负责可靠调度、提醒、错过补偿、跟进和运行日志，再通过 OpenClaw/Hermes 等 agent 适配层把自然语言需求变成结构化任务。

## 当前 v1 骨架

- Python `xushi-daemon`：FastAPI 本地 HTTP API、SQLite 持久化、任务模型、调度计算、跟进策略。
- CLI：`xushi init/doctor/create/list/trigger/tick/executor/notifications`。
- 本地 Web 管理台：访问 daemon 根路径，可查看任务和运行记录。
- OpenClaw 插件：`plugins/openclaw-xushi`，注册健康检查、创建任务、查询任务、手动触发等工具。
- 日历能力：内置中国大陆 2026 年节假日和调休数据，按节日名称分组，来源为国务院办公厅通知。
- 通知记录：提醒触发时生成通知事件，可通过 API、CLI 和 Web 管理台查看。
- 后台扫描：daemon 启动后每 30 秒自动扫描到期任务和未确认跟进。
- 调度语义：支持 asap、窗口任务、截止任务、待规划 floating 任务、完成确认锚点和中国工作日顺延。
- Agent 可靠性：支持 `idempotency_key` 防重复创建，API 成功和错误响应都使用统一 JSON 结构。

## 本地开发

```powershell
uv sync
uv run xushi init --show-token
uv run xushi-daemon
```

访问：

- Web 管理台：`http://127.0.0.1:8766/`
- 健康检查：`http://127.0.0.1:8766/api/v1/health`

诊断本地配置和端口：

```powershell
uv run xushi doctor
```

可选环境变量：

- `XUSHI_CONFIG_PATH`：默认 `~/.xushi/config.json`
- `XUSHI_PORT`：默认 `8766`
- `XUSHI_SCHEDULER_INTERVAL_SECONDS`：默认 `30`
- `XUSHI_DATABASE_PATH`：默认 `~/.xushi/xushi.db`
- `XUSHI_API_TOKEN`：覆盖配置文件中的本地 token

`xushi init` 会生成本地 token 并写入配置文件；默认输出只展示脱敏 token。需要把 token 配给 OpenClaw 时，可使用 `--show-token` 显示完整值。

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

OpenClaw/Hermes executor 支持两种真实触发方式：

```json
{
  "id": "openclaw",
  "kind": "openclaw",
  "name": "OpenClaw",
  "config": {
    "webhook_url": "http://127.0.0.1:3000/hooks/xushi",
    "token": "local-secret",
    "timeout_seconds": 30
  },
  "enabled": true
}
```

```json
{
  "id": "hermes",
  "kind": "hermes",
  "name": "Hermes",
  "config": {
    "command": "hermes agent run --stdin",
    "timeout_seconds": 60
  },
  "enabled": true
}
```

保存执行器：

```powershell
uv run xushi executor .\executor.openclaw.json
```

未配置 `webhook_url` 或 `command` 时，OpenClaw/Hermes executor 会明确返回失败，不会假装触发成功。

Webhook 请求体格式：

```json
{
  "executor": {
    "id": "openclaw",
    "kind": "openclaw",
    "name": "OpenClaw"
  },
  "payload": {
    "prompt": "生成日报"
  }
}
```

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
```

## 分发构建

生成 Python wheel：

```powershell
uv build --wheel
```

生成本机预编译二进制需要 PyInstaller：

```powershell
uv run --with pyinstaller python scripts/build_binaries.py
```

仓库内置 `.github/workflows/build.yml`，会在 Windows、macOS、Linux 上运行测试、lint、wheel 构建和 PyInstaller 二进制构建，并上传构建产物。
