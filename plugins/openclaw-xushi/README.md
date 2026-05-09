# 序时 OpenClaw 插件

本插件把 OpenClaw 连接到本机 `xushi-daemon`，让 agent 可以创建、查询和触发结构化日程任务。

## 工具

- `xushi_health`：检查 daemon 是否在线。
- `xushi_create_task`：创建结构化任务。
- `xushi_list_tasks`：列出任务。
- `xushi_get_task`：查看任务。
- `xushi_trigger_task`：手动触发任务。
- `xushi_confirm_run`：确认运行记录已完成，停止后续跟进。
- `xushi_callback_run`：提交长任务最终结果。
- `xushi_list_executors`：列出执行器配置。
- `xushi_save_executor`：创建或更新执行器配置。
- `xushi_install_hint`：返回安装和启动指引。

## 配置

先初始化序时本地配置：

```powershell
xushi init --show-token
xushi doctor
xushi-daemon
```

默认读取：

- `XUSHI_BASE_URL`：默认 `http://127.0.0.1:8766`
- `XUSHI_API_TOKEN`：本地 API token

OpenClaw config 可覆盖：

```json
{
  "plugins": {
    "entries": {
      "xushi": {
        "enabled": true,
        "config": {
          "baseUrl": "http://127.0.0.1:8766",
          "tokenEnv": "XUSHI_API_TOKEN"
        }
      }
    }
  }
}
```

如果 daemon 未启动或 token 未配置，先运行 `xushi_install_hint` 查看当前插件读取的地址和 token 环境变量名。

## 提醒投递到 Agent

序时 daemon 不能自动调用 OpenClaw 插件本身。要让提醒进入 OpenClaw/飞书等 agent 渠道，必须满足两点：

1. 使用 `xushi_save_executor` 或 CLI 注册 `openclaw` 执行器，并配置 `webhook_url` 或 `command`。
2. 创建提醒任务时在 `task.action.executor_id` 中引用该执行器，例如 `"executor_id": "openclaw"`。

没有 `executor_id` 的 `reminder` 只会走本地系统通知，适合桌面环境，不适合无桌面的服务器。
