"""序时 agent 能力发现清单。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from xushi import __version__

Capability = dict[str, Any]

CAPABILITIES: tuple[Capability, ...] = (
    {
        "id": "discover_capabilities",
        "purpose": "发现当前 xushi 版本面向 agent 暴露的 CLI、HTTP API 和插件能力。",
        "http": {"method": "GET", "path": "/api/v1/capabilities", "auth_required": False},
        "cli": {"command": "xushi capabilities"},
        "openclaw_plugin": {"tool": "xushi_capabilities"},
        "notes": ["HTTP-only agents can also inspect /openapi.json or /docs."],
    },
    {
        "id": "health_check",
        "purpose": "检查 daemon 是否可达。",
        "http": {"method": "GET", "path": "/api/v1/health", "auth_required": False},
        "cli": {"command": "xushi doctor"},
        "openclaw_plugin": {"tool": "xushi_health"},
    },
    {
        "id": "initialize_config",
        "purpose": "初始化本地配置、数据库路径和 API token。",
        "cli": {"command": "xushi init --show-token"},
        "openclaw_plugin": {"tool": "xushi_install_hint"},
        "notes": ["HTTP API cannot initialize its own auth token."],
    },
    {
        "id": "diagnose_config",
        "purpose": "检查本地配置、端口、数据库目录和 executor token 可用性。",
        "cli": {"command": "xushi doctor"},
        "openclaw_plugin": {"tool": "xushi_install_hint"},
    },
    {
        "id": "create_task",
        "purpose": "创建结构化任务。",
        "http": {"method": "POST", "path": "/api/v1/tasks", "auth_required": True},
        "cli": {"command": "xushi create <task.json>"},
        "openclaw_plugin": {"tool": "xushi_create_task"},
    },
    {
        "id": "list_tasks",
        "purpose": "列出任务。",
        "http": {
            "method": "GET",
            "path": "/api/v1/tasks?limit=100",
            "auth_required": True,
        },
        "cli": {"command": "xushi list --limit 100"},
        "openclaw_plugin": {"tool": "xushi_list_tasks"},
    },
    {
        "id": "get_task",
        "purpose": "查看单个任务详情。",
        "http": {"method": "GET", "path": "/api/v1/tasks/{task_id}", "auth_required": True},
        "cli": {"command": "xushi get <task_id>"},
        "openclaw_plugin": {"tool": "xushi_get_task"},
    },
    {
        "id": "update_task",
        "purpose": "部分更新任务配置。",
        "http": {"method": "PATCH", "path": "/api/v1/tasks/{task_id}", "auth_required": True},
        "cli": {"command": "xushi update <task_id> <patch.json>"},
        "openclaw_plugin": {"tool": "xushi_update_task"},
    },
    {
        "id": "archive_task",
        "purpose": "归档任务并取消同任务仍打开的运行记录。",
        "http": {"method": "DELETE", "path": "/api/v1/tasks/{task_id}", "auth_required": True},
        "cli": {"command": "xushi delete <task_id>"},
        "openclaw_plugin": {"tool": "xushi_delete_task"},
    },
    {
        "id": "trigger_task",
        "purpose": "手动触发任务, 用于测试或立即执行; 不要把它当作完成确认。",
        "http": {"method": "POST", "path": "/api/v1/tasks/{task_id}/runs", "auth_required": True},
        "cli": {"command": "xushi trigger <task_id>"},
        "openclaw_plugin": {"tool": "xushi_trigger_task"},
        "notes": [
            "When the user says a task is done, use complete_task, "
            "confirm_latest_run or confirm_run."
        ],
    },
    {
        "id": "complete_task",
        "purpose": (
            "用户说明某任务已完成时, 按任务记录完成。若已有未完成主 run 则确认它; "
            "若 completion anchor 循环任务尚未到点, 则创建不投递的手动完成锚点。"
        ),
        "http": {
            "method": "POST",
            "path": "/api/v1/tasks/{task_id}/complete",
            "auth_required": True,
        },
        "cli": {"command": "xushi complete <task_id>"},
        "openclaw_plugin": {"tool": "xushi_complete_task"},
        "notes": ["Preferred when the user may have completed the task before the next reminder."],
    },
    {
        "id": "list_runs",
        "purpose": "列出运行记录, 可按任务、状态、活跃状态和条数过滤。",
        "http": {
            "method": "GET",
            "path": "/api/v1/runs?task_id=<id>&active_only=true&limit=10",
            "auth_required": True,
        },
        "cli": {"command": "xushi runs --task-id <id> --active-only --limit 10"},
        "openclaw_plugin": {"tool": "xushi_list_runs"},
    },
    {
        "id": "confirm_latest_run",
        "purpose": "用户说明某任务已完成时, 确认该任务最近一次待确认主运行记录。",
        "http": {
            "method": "POST",
            "path": "/api/v1/tasks/{task_id}/runs/confirm-latest",
            "auth_required": True,
        },
        "cli": {"command": "xushi confirm-latest <task_id>"},
        "openclaw_plugin": {"tool": "xushi_confirm_latest_run"},
        "notes": ["Preferred when the agent knows task_id but not run_id."],
    },
    {
        "id": "confirm_run",
        "purpose": "通过 run_id 确认单条运行记录已完成, 并停止同源跟进。",
        "http": {"method": "POST", "path": "/api/v1/runs/{run_id}/confirm", "auth_required": True},
        "cli": {"command": "xushi confirm <run_id>"},
        "openclaw_plugin": {"tool": "xushi_confirm_run"},
    },
    {
        "id": "callback_run",
        "purpose": "外部 agent 异步完成长任务后回填成功或失败结果。",
        "http": {"method": "POST", "path": "/api/v1/runs/{run_id}/callback", "auth_required": True},
        "cli": {"command": "xushi callback <run_id> --status succeeded --result-file result.json"},
        "openclaw_plugin": {"tool": "xushi_callback_run"},
    },
    {
        "id": "list_notifications",
        "purpose": "列出本地通知记录。",
        "http": {"method": "GET", "path": "/api/v1/notifications", "auth_required": True},
        "cli": {"command": "xushi notifications"},
        "openclaw_plugin": {"tool": "xushi_list_notifications"},
    },
    {
        "id": "list_deliveries",
        "purpose": "列出投递计划, 排查延迟、聚合、失败、跳过或静默投递。",
        "http": {"method": "GET", "path": "/api/v1/deliveries?limit=100", "auth_required": True},
        "cli": {"command": "xushi deliveries --limit 100"},
        "openclaw_plugin": {"tool": "xushi_list_deliveries"},
    },
    {
        "id": "retry_deliveries",
        "purpose": "修复 executor 配置后重试 failed delivery。",
        "http": {"method": "POST", "path": "/api/v1/deliveries/retry", "auth_required": True},
        "cli": {"command": "xushi retry-deliveries --limit 10"},
        "openclaw_plugin": {"tool": "xushi_retry_deliveries"},
    },
    {
        "id": "reload_config",
        "purpose": "热加载 executor、全局免打扰和自动重试配置。",
        "http": {"method": "POST", "path": "/api/v1/config/reload", "auth_required": True},
        "cli": {"command": "xushi reload-config"},
        "openclaw_plugin": {"tool": "xushi_reload_config"},
    },
    {
        "id": "list_executors",
        "purpose": "查看当前 daemon 运行时加载的 executor。",
        "http": {"method": "GET", "path": "/api/v1/executors", "auth_required": True},
        "cli": {"command": "xushi executors"},
        "openclaw_plugin": {"tool": "xushi_list_executors"},
    },
    {
        "id": "metrics",
        "purpose": "查看 daemon 进程内运行指标和最近 tick 摘要。",
        "http": {"method": "GET", "path": "/api/v1/metrics", "auth_required": True},
        "notes": [
            "CLI-only agents can use xushi runs, deliveries and notifications for audit data."
        ],
    },
)


def capabilities_payload() -> dict[str, Any]:
    """返回面向 agent 的能力发现响应。"""
    return {
        "name": "xushi",
        "version": __version__,
        "auth": {
            "header": "Authorization: Bearer <XUSHI_API_TOKEN>",
            "token_env": "XUSHI_API_TOKEN",
        },
        "entrypoints": {
            "http": {
                "capabilities": "GET /api/v1/capabilities",
                "openapi": "GET /openapi.json",
                "docs": "GET /docs",
            },
            "cli": {
                "capabilities": "xushi capabilities",
                "help": "xushi --help",
            },
            "openclaw_plugin": {
                "capabilities": "xushi_capabilities",
                "help": "xushi_install_hint",
            },
        },
        "capabilities": deepcopy(CAPABILITIES),
    }
