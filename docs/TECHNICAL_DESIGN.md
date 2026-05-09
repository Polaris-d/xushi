# 序时 xushi 技术方案文档

## 1. 架构概览

序时 v1 采用混合架构：

- `xushi-daemon`：Python 本地服务，负责调度、存储、执行器调用、跟进和 API。
- `xushi` CLI：命令行客户端，复用同一应用服务。
- 本地 Web 管理台：由 daemon 提供，用于查看任务和运行记录。
- OpenClaw 插件：TypeScript 原生插件，运行在 OpenClaw 内，将 agent 工具调用转发到本地 daemon。

```mermaid
flowchart LR
    User["用户"] --> Agent["OpenClaw / Hermes"]
    Agent --> Plugin["xushi agent 插件"]
    Plugin --> API["127.0.0.1 HTTP API"]
    CLI["xushi CLI"] --> API
    Web["本地 Web 管理台"] --> API
    API --> Service["xushi service"]
    Service --> Store["SQLite"]
    Service --> Scheduler["Scheduler"]
    Service --> Executor["Executor Registry"]
```

## 2. 技术栈

- Python 3.12+，当前开发环境为 Python 3.14。
- `uv` 管理依赖和运行命令。
- FastAPI 提供本地 HTTP API。
- SQLite 存储任务、运行记录和通知事件；executor 配置由本地配置文件管理。
- Pydantic 定义结构化任务契约。
- `python-dateutil` 解析 RRULE。
- Typer 提供 CLI。
- OpenClaw 插件使用 TypeScript/ESM。
- PyInstaller 用于生成 `xushi` 与 `xushi-daemon` 跨平台预编译二进制。

## 3. 核心模块

- `xushi.models`：任务、调度、跟进、运行记录、执行器模型。
- `xushi.scheduler`：计算到期触发、错过补偿和未完成跟进。
- `xushi.calendar`：中国工作日日历与调休判断。
- `xushi.storage`：SQLite 持久化。
- `xushi.config`：配置文件、环境变量覆盖和本地 token 初始化。
- `xushi.service`：应用服务层。
- `xushi.api`：本地 HTTP API 和 Web 管理台。
- `xushi.cli`：命令行入口。
- `xushi.upgrade`：手动 CLI 安全升级、备份和回滚。
- `plugins/openclaw-xushi`：OpenClaw 原生插件。
- `xushi.executors`：OpenClaw 执行器调用；Hermes 和通用 webhook executor 暂时仅保留预留位置。

## 4. API 设计

默认绑定 `127.0.0.1:18766`，通过 `Authorization: Bearer <token>` 鉴权。

- `GET /api/v1/health`
- `POST /api/v1/tasks`
- `GET /api/v1/tasks`
- `GET /api/v1/tasks/{id}`
- `PATCH /api/v1/tasks/{id}`
- `DELETE /api/v1/tasks/{id}`
- `POST /api/v1/tasks/{id}/runs`
- `GET /api/v1/runs`
- `POST /api/v1/runs/{id}/confirm`
- `POST /api/v1/runs/{id}/callback`
- `GET /api/v1/notifications`
- `GET /api/v1/executors` 是只读接口，返回当前 `config.json` 加载的 executor 配置。

成功和错误响应都使用统一结构：

```json
{
  "status": 200,
  "code": 200,
  "message": "ok",
  "data": {},
  "errors": []
}
```

## 5. 数据模型

SQLite 当前以 JSON payload 方式保存核心对象，便于 v1 快速演进 schema。后续稳定后可拆分索引字段。

- `tasks`：任务 payload、状态、创建时间、更新时间。
- `runs`：运行记录 payload、任务 ID、调度时间、状态。
- `notifications`：通知事件 payload、创建时间、投递状态。

SQLite 连接按操作短连接打开并立即关闭，避免 Windows 下 daemon、测试或安装器清理数据文件时遇到文件句柄占用。

配置优先级为环境变量高于配置文件高于默认值。默认配置文件位于状态目录下的 `config.json`，`xushi init` 可生成本地 token、SQLite 路径、监听地址、端口、后台扫描间隔和默认 executor 列表；`xushi doctor` 用于检查配置文件、数据库目录和端口占用，帮助 agent 插件给出可执行的错误提示。

Executor 是本地配置，不属于运行态数据。`Settings.executors` 从 `config.json` 的 `executors` 数组加载，service 在启动时构建启用 executor 映射；修改 executor 配置后需要重启 daemon。`GET /api/v1/executors` 和 CLI `xushi executors` 只用于查看当前配置，不提供写入接口，避免 agent 在运行时把投递凭据或外部入口写入 SQLite。

OpenClaw executor 是 v1 唯一实现的 agent 回传路径。`mode=hooks_agent` 时，序时将 `action.payload` 转换为 OpenClaw `/hooks/agent` 请求体，字段包括 `message`、`name`、`agentId`、`wakeMode`、`deliver`、`channel`、`to`、`model`、`fallbacks`、`thinking` 和 `timeoutSeconds`。executor config 使用 snake_case，例如 `agent_id`、`wake_mode`、`timeout_seconds`，同时兼容 OpenClaw 的 camelCase 字段。token 优先从 executor 的 `token` 读取，其次从 `token_env` 或默认环境变量 `OPENCLAW_HOOKS_TOKEN` / `OPENCLAW_WEBHOOK_TOKEN` 读取。`insecure_tls` 默认 false，只有 OpenClaw Gateway 使用本机自签名 HTTPS 时才应显式启用。Hermes 和通用 webhook executor 暂时仅保留 schema 位置，调用时返回 `reserved but not implemented`，不进行网络投递。v1 不提供 command executor，避免跨平台 shell、命令注入和环境差异扩大配置复杂度。`reminder` action 在配置 `executor_id` 时会走对应 executor；没有 `executor_id` 时才走本地系统通知。

长任务可在启动后异步回调 `POST /api/v1/runs/{id}/callback`，将运行记录更新为 `succeeded` 或 `failed`，并合并最终结果。

`Run` 使用 `origin_run_id` 将跟进记录关联到原始运行记录。用户或 agent 确认任一跟进记录后，序时会同步确认原始运行记录，后续跟进停止。

中国大陆 2026 年节假日数据存放在 `xushi/data/china_holidays_2026.json`，来源为国务院办公厅《关于2026年部分节假日安排的通知》。数据按节日名称分组，`holidays` 和 `adjusted_workdays` 均包含 `name` 与 `dates`，运行时展开为 `date -> name` 映射。`ChinaWorkdayCalendar.holiday_name()` 返回法定节假日名称，`adjusted_workday_name()` 返回调休工作日关联的节日名称。

## 6. 可靠性策略

- 调度语义采用“至少触发一次”。
- 每次触发创建 `Run` 记录。
- `missed_policy=catch_up_latest` 默认只补最近一次错过触发。
- `expiry` 到期后不再补发，适合抢购/抢票。
- `window` 任务在窗口打开时触发一次，窗口结束后不再补发。
- `deadline` 任务在截止时间到达后触发一次；`asap` 任务以任务创建时间作为尽快触发时间；`floating` 任务保留在待规划池，不自动触发。
- `calendar_policy=workday` 使用中国大陆工作日日历，将触发时间顺延到下一个工作日并保留原时刻。
- `anchor=completion` 的循环任务在上一条主运行记录确认完成后，基于确认时间重新计算下一次 RRULE 发生时间；未确认时不会继续生成主运行。
- `idempotency_key` 用于 agent 重试安全，服务层发现同 key 任务时直接返回已有任务。
- `FollowUpPolicy` 控制确认、宽限期、跟进间隔、最大次数和是否询问改期。
- FastAPI lifespan 启动后台调度循环，默认每 30 秒执行一次到期任务和跟进扫描。

## 7. OpenClaw 插件设计

插件目录为 `plugins/openclaw-xushi`。

- `openclaw.plugin.json` 声明插件 ID、配置 schema、工具契约。
- `package.json#openclaw` 声明 TS 源入口和 JS 运行时入口。
- 注册工具：`xushi_health`、`xushi_create_task`、`xushi_list_tasks`、`xushi_get_task`、`xushi_trigger_task`、`xushi_confirm_run`、`xushi_callback_run`、`xushi_list_executors`、`xushi_install_hint`。
- `xushi_list_executors` 只查看当前 `config.json` 加载的 executor；插件不提供保存 executor 工具。
- 插件读取 `XUSHI_BASE_URL` 和 `XUSHI_API_TOKEN`，默认连接本机 daemon。

## 8. 分发设计

- README 使用 GitHub 项目页风格，提供徽章、价值主张、能力表格、快速安装和验证入口。
- `docs/guide/installation.md` 提供两层安装说明：人类复制给 LLM Agent 的短提示词，以及 agent 可执行的分步安装与验证流程。
- `scripts/install.ps1` 和 `scripts/install.sh` 默认安装到用户目录 `~/.xushi/app`，已有 Git 仓库时使用 `git pull --ff-only` 更新，随后执行 `uv sync`、`xushi init --show-token` 和 `xushi doctor`。
- `uv build --wheel` 生成 Python wheel，适合开发者和 Python 用户安装。
- `scripts/build_binaries.py` 通过 PyInstaller 生成 `xushi` 和 `xushi-daemon` 单文件二进制。
- PyInstaller 构建使用 `--collect-data xushi`，确保中国节假日 JSON 等包数据被包含在二进制中。
- `.github/workflows/build.yml` 在 Windows、macOS、Linux 上执行测试、ruff、wheel 构建和二进制构建，并上传已按平台重命名的构建产物，不上传 PyInstaller 临时 `.spec` 文件。
- `scripts/prepare_release_assets.py` 负责将 PyInstaller 二进制重命名为 `xushi-<platform>`、`xushi-daemon-<platform>`，复制 Python wheel/sdist，并打包 OpenClaw 插件 zip。
- `.github/workflows/release.yml` 在 `v*` tag 上先运行跨平台质量检查，再分别构建 Python 包和平台二进制，最后合并 release 资产、生成 `SHA256SUMS.txt` 并发布 GitHub Release 自动说明。
- `xushi upgrade status/check/backup/apply/rollback` 提供用户手动触发的安全升级能力。升级器默认不做静默自动升级；`apply` 当前面向 git 安装目录，先检查 daemon 端口和工作区干净度，再备份配置和 SQLite 数据库，随后执行 `git fetch --tags --prune`、`git checkout --detach <version>` 或 `git pull --ff-only`、`uv sync`。
- 升级备份存放在配置目录的 `backups/upgrade-<timestamp>` 下，包含 `config.json`、通过 SQLite backup API 生成的一致性数据库快照、存在的 WAL/SHM sidecar 和 `manifest.json`。`rollback` 根据 manifest 恢复原路径，恢复主数据库前会清理现有 WAL/SHM sidecar，避免旧 sidecar 干扰恢复数据。
- `.gitattributes` 固定 shell、Python、Markdown、YAML、JSON、TOML、TS/JS 为 LF，PowerShell 脚本为 CRLF，避免跨平台安装脚本换行损坏。
- 项目根目录提供 MIT License，`pyproject.toml` 声明 `license = "MIT"`。
- 项目根目录提供 `CONTRIBUTING.md` 和 `SECURITY.md`，`.github` 下提供 Issue 模板和 PR 模板，统一外部反馈格式。

## 9. 方案变更记录

| 日期 | 类型 | 内容 |
| ---- | ---- | ---- |
| 2026-05-09 | 新增 | 创建 Python daemon + TypeScript OpenClaw 插件的 v1 技术方案。 |
| 2026-05-09 | 明确 | 增加后台调度循环、运行记录确认接口、跟进记录关联和 OpenClaw 确认工具。 |
| 2026-05-09 | 明确 | 增加数据文件驱动的中国大陆 2026 年节假日与调休日历。 |
| 2026-05-09 | 明确 | OpenClaw executor 从模板占位升级为真实投递探索，后续收敛到 `/hooks/agent`。 |
| 2026-05-09 | 新增 | 增加长任务 callback API 和 OpenClaw callback 工具。 |
| 2026-05-09 | 新增 | 增加配置文件初始化、环境变量覆盖和 CLI doctor 诊断设计。 |
| 2026-05-09 | 明确 | 实现窗口、截止、待规划、完成锚点和工作日顺延调度规则。 |
| 2026-05-09 | 新增 | 增加 asap 调度、幂等创建和统一 API 错误响应。 |
| 2026-05-09 | 新增 | 增加 PyInstaller 二进制构建脚本和跨平台 CI 构建工作流。 |
| 2026-05-09 | 调整 | 中国大陆节假日数据结构改为按节日名称分组，并在日历模块暴露节日名称查询。 |
| 2026-05-09 | 新增 | 增加 GitHub 风格 README、MIT License、agent 安装指南和跨平台安装脚本。 |
| 2026-05-09 | 新增 | 增加 `.gitattributes` 跨平台换行规范和 tag 发布 Release 工作流。 |
| 2026-05-09 | 新增 | 增加社区健康文件、Issue 模板和 PR 模板。 |
| 2026-05-09 | 更正 | 修复 reminder action 忽略 executor 的路由问题，并补充 OpenClaw executor 接入能力。 |
| 2026-05-10 | 更正 | 撤回早期 command bridge 方案，避免跨平台和安全边界复杂度。 |
| 2026-05-10 | 调整 | OpenClaw 默认投递链路从 TaskFlow webhook 调整为 `/hooks/agent`，并新增 `hooks_agent` 载荷适配。 |
| 2026-05-10 | 调整 | 移除 command executor；Hermes 和通用 webhook executor 暂时仅返回预留未实现状态。 |
| 2026-05-10 | 明确 | 完善 OpenClaw `/hooks/agent` 可选字段映射，支持 snake_case 与 camelCase 配置别名。 |
| 2026-05-10 | 调整 | OpenClaw HTTPS 自签名证书改为显式 `insecure_tls` 配置，默认保持 TLS 证书校验。 |
| 2026-05-10 | 调整 | executor 配置从 SQLite/API 写入调整为 `config.json` 管理，API 和 OpenClaw 插件仅保留只读查看能力。 |
| 2026-05-10 | 调整 | 默认 daemon 端口从 `8766` 调整为 `18766`，避开低位常见开发端口并保留旧端口记忆点。 |
| 2026-05-10 | 调整 | 重构 GitHub Release workflow，拆分质量检查、Python 包、平台二进制和发布步骤，增加唯一资产命名、插件 zip 和 SHA256 校验和。 |
| 2026-05-10 | 新增 | 增加手动 CLI 安全升级设计，提供 status/check/backup/apply/rollback，并在升级前使用 SQLite backup API 创建可回滚备份。 |
