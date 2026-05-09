import { Type } from "@sinclair/typebox";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const DEFAULT_BASE_URL = "http://127.0.0.1:8766";

function textResult(value) {
  return { content: [{ type: "text", text: JSON.stringify(value, null, 2) }] };
}

function resolveConfig(api = {}) {
  return {
    baseUrl: api.config?.baseUrl ?? process.env.XUSHI_BASE_URL ?? DEFAULT_BASE_URL,
    tokenEnv: api.config?.tokenEnv ?? "XUSHI_API_TOKEN",
  };
}

async function xushiRequest(config, path, init = {}) {
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
        "创建结构化序时任务。请先把用户自然语言转换为 xushi task schema：schedule 必须包含 timezone；尽快任务用 asap，一次性任务用 ISO run_at，循环任务用 RRULE。若用户希望提醒通过 OpenClaw/飞书等 agent 渠道送达，请先配置 executor，并在 task.action.executor_id 中引用它。",
      parameters: Type.Object({
        task: Type.Record(Type.String(), Type.Any(), {
          description: "符合 xushi TaskCreate schema 的任务 JSON。",
        }),
      }),
      async execute(_id, params) {
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
      parameters: Type.Object({}),
      async execute() {
        return textResult(await xushiRequest(config, "/api/v1/tasks"));
      },
    });

    api.registerTool({
      name: "xushi_get_task",
      description: "查看单个 xushi 任务详情。",
      parameters: Type.Object({
        task_id: Type.String({ description: "xushi 任务 ID。" }),
      }),
      async execute(_id, params) {
        return textResult(await xushiRequest(config, `/api/v1/tasks/${params.task_id}`));
      },
    });

    api.registerTool({
      name: "xushi_trigger_task",
      description: "手动触发一个 xushi 任务，用于测试或立即执行。",
      parameters: Type.Object({
        task_id: Type.String({ description: "xushi 任务 ID。" }),
      }),
      async execute(_id, params) {
        return textResult(
          await xushiRequest(config, `/api/v1/tasks/${params.task_id}/runs`, { method: "POST" }),
        );
      },
    });

    api.registerTool({
      name: "xushi_confirm_run",
      description: "确认一个 xushi run 已完成，用于停止后续跟进提醒。",
      parameters: Type.Object({
        run_id: Type.String({ description: "xushi 运行记录 ID。" }),
      }),
      async execute(_id, params) {
        return textResult(
          await xushiRequest(config, `/api/v1/runs/${params.run_id}/confirm`, { method: "POST" }),
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
      async execute(_id, params) {
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
      description: "列出本机 xushi 执行器配置，用于确认 OpenClaw/Hermes/webhook/command 投递链路是否可用。",
      parameters: Type.Object({}),
      async execute() {
        return textResult(await xushiRequest(config, "/api/v1/executors"));
      },
    });

    api.registerTool({
      name: "xushi_save_executor",
      description:
        "创建或更新 xushi 执行器。OpenClaw/Hermes executor 必须配置 webhook_url 或 command，否则 daemon 无法主动把提醒发给 agent。",
      parameters: Type.Object({
        executor: Type.Record(Type.String(), Type.Any(), {
          description:
            "符合 xushi Executor schema 的 JSON，例如 { id: 'openclaw', kind: 'openclaw', name: 'OpenClaw', config: { webhook_url: 'http://127.0.0.1:3000/hooks/xushi' }, enabled: true }。",
        }),
      }),
      async execute(_id, params) {
        return textResult(
          await xushiRequest(config, "/api/v1/executors", {
            method: "POST",
            body: JSON.stringify(params.executor),
          }),
        );
      },
    });

    api.registerTool(
      {
        name: "xushi_install_hint",
        description: "当 xushi daemon 未安装或未启动时，返回安全的安装与启动指引。",
        parameters: Type.Object({}),
        async execute() {
          return textResult({
            install: "下载 xushi 预编译二进制后运行 xushi init --show-token、xushi doctor、xushi-daemon。",
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
