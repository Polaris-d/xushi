import { Type } from "@sinclair/typebox";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const DEFAULT_BASE_URL = "http://127.0.0.1:18766";

type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

interface XushiConfig {
  baseUrl?: string;
  tokenEnv?: string;
}

function textResult(value: unknown) {
  return { content: [{ type: "text", text: JSON.stringify(value, null, 2) }] };
}

function resolveConfig(api: { config?: XushiConfig } = {}): Required<XushiConfig> {
  return {
    baseUrl: api.config?.baseUrl ?? process.env.XUSHI_BASE_URL ?? DEFAULT_BASE_URL,
    tokenEnv: api.config?.tokenEnv ?? "XUSHI_API_TOKEN",
  };
}

function withQuery(
  path: string,
  query: Record<string, boolean | number | string | undefined>,
) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === "") {
      continue;
    }
    params.set(key, String(value));
  }
  const suffix = params.toString();
  return suffix ? `${path}?${suffix}` : path;
}

async function xushiRequest(config: Required<XushiConfig>, path: string, init: RequestInit = {}) {
  const token = process.env[config.tokenEnv];
  if (!token) {
    throw new Error(
      `Missing ${config.tokenEnv}; run xushi init --show-token, export the local token, then start xushi-daemon.`,
    );
  }
  const response = await fetch(`${config.baseUrl}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
      ...(init.headers ?? {}),
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`xushi request failed: ${response.status} ${JSON.stringify(body)}`);
  }
  return body;
}

export default definePluginEntry({
  id: "xushi",
  name: "序时 xushi",
  description: "Create and manage reliable local schedules through the xushi daemon.",
  register(api) {
    const config = resolveConfig(api);

    api.registerTool({
      name: "xushi_capabilities",
      description:
        "列出当前 xushi daemon 面向 agent 暴露的 HTTP API、CLI 命令和插件工具。使用不熟悉的流程前先调用它。",
      parameters: Type.Object({}),
      async execute() {
        const response = await fetch(`${config.baseUrl}/api/v1/capabilities`);
        return textResult(await response.json());
      },
    });

    api.registerTool({
      name: "xushi_health",
      description: "检查本机 xushi daemon 是否在线。",
      parameters: Type.Object({}),
      async execute() {
        const response = await fetch(`${config.baseUrl}/api/v1/health`);
        return textResult({ ok: response.ok, status: response.status, body: await response.json() });
      },
    });

    api.registerTool({
      name: "xushi_create_task",
      description:
        "创建结构化序时任务。请先把用户自然语言转换为 xushi task schema：所有具体时间必须带时区偏移，schedule 必须包含 IANA timezone；尽快任务用 asap，一次性任务用 ISO run_at，循环任务用 RRULE，BYHOUR/BYMINUTE 按 schedule.timezone 解释。免打扰属于 quiet_policy / delivery 层，普通任务默认继承全局 quiet_policy；明确夜间提醒才设置 quiet_policy.mode=bypass。若用户希望提醒通过 OpenClaw/飞书等 agent 渠道送达，请先在 ~/.xushi/config.json 配置 executor，并在 task.action.executor_id 中引用它。",
      parameters: Type.Object({
        task: Type.Record(Type.String(), Type.Any(), {
          description: "符合 xushi TaskCreate schema 的任务 JSON。",
        }),
      }),
      async execute(_id, params: { task: JsonValue }) {
        return textResult(
          await xushiRequest(config, "/api/v1/tasks", {
            method: "POST",
            body: JSON.stringify(params.task),
          }),
        );
      },
    });

    api.registerTool({
      name: "xushi_list_tasks",
      description: "列出本机 xushi 任务。",
      parameters: Type.Object({
        limit: Type.Optional(Type.Number({ description: "最多返回多少条。" })),
      }),
      async execute(_id, params: { limit?: number }) {
        return textResult(await xushiRequest(config, withQuery("/api/v1/tasks", params)));
      },
    });

    api.registerTool({
      name: "xushi_get_task",
      description: "查看单个 xushi 任务详情。",
      parameters: Type.Object({
        task_id: Type.String({ description: "xushi 任务 ID。" }),
      }),
      async execute(_id, params: { task_id: string }) {
        return textResult(await xushiRequest(config, `/api/v1/tasks/${params.task_id}`));
      },
    });

    api.registerTool({
      name: "xushi_update_task",
      description: "部分更新 xushi 任务。patch 必须符合 xushi TaskPatch schema。",
      parameters: Type.Object({
        task_id: Type.String({ description: "xushi 任务 ID。" }),
        patch: Type.Record(Type.String(), Type.Any(), {
          description: "符合 xushi TaskPatch schema 的部分更新 JSON。",
        }),
      }),
      async execute(_id, params: { task_id: string; patch: JsonValue }) {
        return textResult(
          await xushiRequest(config, `/api/v1/tasks/${params.task_id}`, {
            method: "PATCH",
            body: JSON.stringify(params.patch),
          }),
        );
      },
    });

    api.registerTool({
      name: "xushi_delete_task",
      description: "归档 xushi 任务，并取消该任务仍打开的运行记录。",
      parameters: Type.Object({
        task_id: Type.String({ description: "xushi 任务 ID。" }),
      }),
      async execute(_id, params: { task_id: string }) {
        return textResult(
          await xushiRequest(config, `/api/v1/tasks/${params.task_id}`, { method: "DELETE" }),
        );
      },
    });

    api.registerTool({
      name: "xushi_trigger_task",
      description: "手动触发一个 xushi 任务，用于测试或立即执行。",
      parameters: Type.Object({
        task_id: Type.String({ description: "xushi 任务 ID。" }),
      }),
      async execute(_id, params: { task_id: string }) {
        return textResult(
          await xushiRequest(config, `/api/v1/tasks/${params.task_id}/runs`, { method: "POST" }),
        );
      },
    });

    api.registerTool({
      name: "xushi_list_runs",
      description:
        "列出 xushi 运行记录。可按 task_id、status、active_only 和 limit 过滤；agent 判断待确认事项时优先用 active_only=true。",
      parameters: Type.Object({
        task_id: Type.Optional(Type.String({ description: "按任务 ID 过滤。" })),
        status: Type.Optional(
          Type.Union([
            Type.Literal("pending_delivery"),
            Type.Literal("succeeded"),
            Type.Literal("failed"),
            Type.Literal("pending_confirmation"),
            Type.Literal("following_up"),
            Type.Literal("cancelled"),
          ]),
        ),
        active_only: Type.Optional(Type.Boolean({ description: "只返回仍需处理的运行记录。" })),
        limit: Type.Optional(Type.Number({ description: "最多返回多少条。" })),
      }),
      async execute(
        _id,
        params: {
          task_id?: string;
          status?: string;
          active_only?: boolean;
          limit?: number;
        },
      ) {
        return textResult(await xushiRequest(config, withQuery("/api/v1/runs", params)));
      },
    });

    api.registerTool({
      name: "xushi_list_notifications",
      description: "列出 xushi 本地通知记录，用于排查未配置 executor 时的本地通知链路。",
      parameters: Type.Object({}),
      async execute() {
        return textResult(await xushiRequest(config, "/api/v1/notifications"));
      },
    });

    api.registerTool({
      name: "xushi_list_deliveries",
      description:
        "列出 xushi 投递计划。用于查看 run 是否已投递、被免打扰延迟、被摘要聚合、跳过、静默或失败。",
      parameters: Type.Object({
        limit: Type.Optional(Type.Number({ description: "最多返回多少条。" })),
      }),
      async execute(_id, params: { limit?: number }) {
        return textResult(await xushiRequest(config, withQuery("/api/v1/deliveries", params)));
      },
    });

    api.registerTool({
      name: "xushi_retry_deliveries",
      description:
        "重试仍需要投递的 failed delivery。修复 executor token、URL、TLS 或 agent_id 配置后，先 reload config 或按需重启 daemon，再使用。",
      parameters: Type.Object({
        limit: Type.Optional(Type.Number({ description: "最多重试多少条 failed delivery。" })),
      }),
      async execute(_id, params: { limit?: number }) {
        return textResult(
          await xushiRequest(config, withQuery("/api/v1/deliveries/retry", params), {
            method: "POST",
          }),
        );
      },
    });

    api.registerTool({
      name: "xushi_reload_config",
      description:
        "显式重新加载 xushi config.json 中的 executors 和全局 quiet_policy。API token、数据库路径、监听端口和调度间隔仍需要重启 daemon。",
      parameters: Type.Object({}),
      async execute() {
        return textResult(
          await xushiRequest(config, "/api/v1/config/reload", { method: "POST" }),
        );
      },
    });

    api.registerTool({
      name: "xushi_confirm_run",
      description: "确认一个 xushi run 已完成，用于停止后续跟进提醒。",
      parameters: Type.Object({
        run_id: Type.String({ description: "xushi 运行记录 ID。" }),
      }),
      async execute(_id, params: { run_id: string }) {
        return textResult(
          await xushiRequest(config, `/api/v1/runs/${params.run_id}/confirm`, { method: "POST" }),
        );
      },
    });

    api.registerTool({
      name: "xushi_confirm_latest_run",
      description:
        "确认某个任务最近一次待确认的主运行记录。用户说已完成某个任务时，优先用它，避免先查 run_id。",
      parameters: Type.Object({
        task_id: Type.String({ description: "xushi 任务 ID。" }),
      }),
      async execute(_id, params: { task_id: string }) {
        return textResult(
          await xushiRequest(config, `/api/v1/tasks/${params.task_id}/runs/confirm-latest`, {
            method: "POST",
          }),
        );
      },
    });

    api.registerTool({
      name: "xushi_callback_run",
      description: "提交长任务最终结果。用于 agent 异步完成后把 run 更新为 succeeded 或 failed。",
      parameters: Type.Object({
        run_id: Type.String({ description: "xushi 运行记录 ID。" }),
        status: Type.Union([Type.Literal("succeeded"), Type.Literal("failed")]),
        result: Type.Optional(Type.Record(Type.String(), Type.Any())),
        error: Type.Optional(Type.String()),
      }),
      async execute(
        _id,
        params: {
          run_id: string;
          status: "succeeded" | "failed";
          result?: JsonValue;
          error?: string;
        },
      ) {
        return textResult(
          await xushiRequest(config, `/api/v1/runs/${params.run_id}/callback`, {
            method: "POST",
            body: JSON.stringify({
              status: params.status,
              result: params.result ?? {},
              error: params.error,
            }),
          }),
        );
      },
    });

    api.registerTool({
      name: "xushi_list_executors",
      description:
        "列出本机 xushi config.json 中的执行器配置，用于确认 OpenClaw /hooks/agent 或 Hermes webhook 投递链路是否可用。",
      parameters: Type.Object({}),
      async execute() {
        return textResult(await xushiRequest(config, "/api/v1/executors"));
      },
    });

    api.registerTool(
      {
        name: "xushi_install_hint",
        description: "当 xushi daemon 未安装或未启动时，返回安全的安装与启动指引。",
        parameters: Type.Object({}),
        async execute() {
          return textResult({
            install:
              "运行 scripts/install.ps1 或 scripts/install.sh，从 GitHub Release 下载二进制并配置全局命令，然后启动 xushi-daemon。",
            devInstall:
              "uv sync; uv run xushi init --show-token; $env:XUSHI_API_TOKEN='<local-token>'; uv run xushi-daemon",
            baseUrl: config.baseUrl,
            tokenEnv: config.tokenEnv,
          });
        },
      },
      { optional: true },
    );
  },
});
