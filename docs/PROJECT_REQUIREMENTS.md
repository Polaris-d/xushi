# 序时 xushi 项目需求文档

## 1. 项目定位

序时是优先适配 OpenClaw 和 Hermes 的本地化日程管理与排期工具，同时兼容其他 agent 工具，提供可靠的本地调度、提醒、补偿、跟进和任务审计能力。

## 2. 目标用户

- 已使用 OpenClaw 或 Hermes 的个人用户，这是 v1 的重点适配人群。
- 已使用其他 agent 工具，并希望复用同一本地调度底座的个人用户。
- 需要本地可靠提醒、循环任务和 agent 定时执行能力的开发者。
- 希望通过开源工具管理个人工作生活排期的高级用户。

## 3. v1 核心需求

- 独立 `xushi-daemon` 常驻进程负责调度，不依赖 agent 自身常驻。
- 默认只监听 `127.0.0.1:18766`，通过本地 token 鉴权。
- 支持结构化任务输入，由 agent 将自然语言转换为序时 schema。
- 支持固定时间、循环任务、时间窗口、截止时间、持续时长、过期策略、完成确认和未完成跟进。
- 支持 `idempotency_key`，保障 agent 重试创建任务时不会重复生成任务；同一幂等键若携带不同请求体，必须返回冲突错误，避免 agent 静默复用错误任务。
- API 成功和错误响应均使用统一 JSON 结构，方便 agent 稳定解析。
- 支持 ISO 8601 时间、RRULE、timezone。
- 支持 ISO 8601 duration 的天、时、分、秒组合，例如 `P1D`、`PT10M`、`P1DT2H`；年月、小数和负数 duration 必须显式拒绝，避免自然月和时区语义歧义。
- API 中所有具体时间点必须携带时区偏移，例如 `Z` 或 `+08:00`；不带时区的时间一律拒绝，服务端不得猜测默认时区。
- 任务必须单独标注 IANA 时区，例如 `Asia/Shanghai`；RRULE、工作日策略、免打扰窗口和摘要投递等本地日历语义都必须按该时区或用户配置的时区解释。
- 支持中国大陆工作日、法定节假日和调休判断；节假日与调休数据必须标注关联节日名称；工作日策略下可将触发时间顺延到下一个中国大陆工作日。
- 支持基于完成确认时间重新计算下一次提醒，适配久坐提醒等 completion anchor 场景。
- `completion` anchor 任务必须启用完成确认；从其他 anchor 切换到 `completion` 时，若最近一条主运行记录已经结束但没有确认时间，必须拒绝更新并要求先建立明确完成锚点。
- 任务到期事实和提醒投递行为必须分层：`Run` 记录到期事实，`Delivery` 记录实际投递计划、延迟、聚合和结果。
- 支持用户级全局免打扰策略，允许多个时间窗口，并支持 `everyday`、`workdays`、`weekends`、`weekdays` 生效规则；`workdays` 必须复用中国大陆工作日和调休判断。
- 支持任务级免打扰策略，默认继承用户级策略；任务可显式覆盖、绕过、跳过或静默处理免打扰。
- 免打扰默认行为为 `delay`，即延迟投递而不是丢弃任务；免打扰结束后的延迟提醒默认聚合为摘要，避免消息轰炸。
- 支持“至少触发一次”的可靠性语义。
- 错过触发时默认只补偿最近一次。
- 每次触发生成可审计运行记录。
- agent/聊天渠道优先通知：提醒任务配置 `executor_id` 时必须通过对应 executor 投递；未配置 executor 的 reminder 仅使用本地系统通知和 Web 管理台记录。
- 内置 OpenClaw、Hermes、webhook executor 概念。
- executor 配置必须存放在本地 `config.json` 的 `executors` 数组中，数据库不保存 executor 配置。
- 修改 `config.json` 中的 `executors` 或全局 `quiet_policy` 后，必须支持通过显式 reload API 重新加载运行时配置，不要求用户重启 daemon。
- 修改自动重试策略后，显式 reload 必须能更新运行时配置；显式 reload 不热更新数据库路径、SQLite PRAGMA、监听地址、端口、API token 和调度间隔，这些启动级配置变更仍要求重启 daemon。
- OpenClaw executor 默认使用 `mode=hooks_agent` 调用 OpenClaw `/hooks/agent`，让 OpenClaw agent 处理提醒文本并通过 `deliver=true` 投递到聊天渠道。
- OpenClaw executor 必须支持 `token_env`，避免把 OpenClaw hook token 写入任务或 executor JSON。
- OpenClaw executor 必须支持 `/hooks/agent` 的可选字段：`name`、`agent_id`、`wake_mode`、`deliver`、`channel`、`to`、`model`、`fallbacks`、`thinking`、`timeout_seconds`。
- OpenClaw executor 必须暴露 `insecure_tls` 配置项；默认保持 TLS 证书校验，仅在用户显式配置本机自签名 HTTPS 时关闭校验。
- Hermes executor 必须支持可配置 HTTP agent webhook，支持 `webhook_url`、`token_env`、`message_field`、`agent_id`、`conversation_id`、`channel`、`deliver` 和请求超时配置。
- 通用 webhook executor v1 仅保留 schema 位置，调用时返回明确未实现状态。
- v1 暂不提供 command executor，避免跨平台 shell、命令注入和环境差异扩大配置复杂度。
- OpenClaw 插件必须提供执行器查看工具；executor 写入由本地 `config.json` 管理，不通过 API 或插件保存。
- 长任务支持执行器异步回调最终结果，更新运行记录成功或失败状态。
- 提供 CLI 和本地 Web 管理台。
- 提供 OpenClaw TypeScript 原生插件。
- 提供本地配置初始化命令，生成本地 token、SQLite 路径和 daemon 端口配置，便于 OpenClaw 插件和用户共享同一连接信息。
- 提供诊断命令，检查配置文件、数据库目录、监听端口和 executor 环境变量/TLS/agent 路由风险，帮助用户定位 daemon 和投递链路问题。
- 提供面向人类复制给 LLM Agent 的安装提示词和 agent 可读安装指南。
- 提供 Windows PowerShell 与 macOS/Linux shell 安装脚本，默认从 GitHub Release 下载预编译二进制并安装到用户本地全局命令目录。
- 安装脚本必须把 `xushi` 和 `xushi-daemon` 配置为用户级全局命令。
- 安装指南必须优先说明 OpenClaw 插件、OpenClaw `/hooks/agent` executor 和 Hermes agent webhook 配置。
- 提供 `xushi-skills` 任务类型指南包，帮助 agent 判断任务类型、生成任务 schema、配置跟进策略并在需求不明确时追问用户。
- 安装指南必须要求 agent 在安装前询问用户是否安装 `xushi-skills`，并明确强烈推荐安装；用户同意后应通过静默参数完成安装，不在脚本执行中二次追问。
- 安装指南必须要求 agent 在配置完成后与用户互动，发送真实测试提醒并确认目标渠道能够正常收到消息，不能只以 `xushi doctor` 作为安装完成标准。
- 安装后的配置引导必须突出易错点：agent/plugin 环境变量作用域、本地 token 是否同步、`xushi-daemon` 是否已 reload 或重启、executor id 是否与 `action.executor_id` 精确匹配、hook URL 是否可从 daemon 访问，以及 OpenClaw/Hermes 渠道路由是否真正送达用户。
- 安装脚本必须支持通过显式参数安装辅助 skill 目标；当前仅支持 `openclaw` 和 `hermes`。文档不得再提供 Codex skill 安装目标。
- 安装脚本必须允许 agent 通过 `XUSHI_OPENCLAW_SKILLS_DIR` / `XUSHI_HERMES_SKILLS_DIR` 或已有的 `OPENCLAW_SKILLS_DIR` / `HERMES_SKILLS_DIR` 指定自定义 skills 根目录，避免不同 agent 目录调整后安装到错误位置。
- 默认不得未经用户授权修改 agent 工具配置。
- 提供用户手动触发的 CLI 安全升级能力；序时不得静默自动升级。
- 手动升级必须先备份 `config.json`、SQLite 数据库和存在的 WAL/SHM sidecar，升级失败时不得丢失旧数据。
- 手动升级必须支持查看状态、检查目标版本、创建备份、从 GitHub Release 下载替换全局命令和从备份恢复。
- 提供 wheel 和跨平台预编译二进制构建配置，降低非 Python 用户安装门槛。
- 提供 tag 触发的 GitHub Release 工作流，发布 wheel 与跨平台二进制产物。
- GitHub Release 资产必须使用唯一、可读的平台命名，并包含自动 release notes 和 SHA256 校验和。
- 预编译二进制必须使用稳定 Python 版本构建，并在发布工作流中执行启动级 smoke test，避免打包运行时与目标系统内核策略不兼容。
- `xushi-skills` 必须随应用程序打包，安装和升级以当前 `xushi` 程序版本为准；GitHub Release 不再发布独立的 `xushi-skills.zip`，避免 skills 与程序版本错配。
- OpenClaw 插件必须随应用程序打包，安装和升级以当前 `xushi` 程序版本为准；GitHub Release 不再发布独立的插件 zip。插件源码目录仍保留，用于开发和 ClawHub 发布。
- 提供 `.gitattributes` 控制跨平台换行，避免 shell 脚本和 CI 配置在 Windows 开发环境中被破坏。
- 项目采用 MIT License 开源。
- 提供贡献指南、安全策略、Issue 模板和 PR 模板，降低外部协作成本。
- daemon 启动后必须自动扫描到期任务和未确认跟进，不能依赖用户手动执行 `tick`。
- daemon 后台调度循环必须输出可观察的启动日志；有触发或跟进创建时应输出 tick 摘要，避免调度器静默导致 agent 无法判断是否运行。
- daemon 必须提供本地运行期指标接口，至少包含 run 创建数、delivery 成功/失败/延迟数、跟进创建数、自动重试数和最近 tick 摘要。
- SQLite 必须保留 JSON payload 的演进弹性，同时把高频查询字段冗余为结构化列并建立索引，用于任务扫描、运行记录确认、delivery 到期投递和幂等键查询。
- SQLite journal mode 和 synchronous 策略必须可配置，默认保持保守；启用 WAL / NORMAL 时需在文档中说明一致性和性能权衡。
- 数据库 schema 必须支持就地迁移，旧版本本地库升级后不得因缺少新增列或索引而无法启动。
- 支持确认运行记录已完成，确认后停止后续跟进提醒。
- 支持按任务、状态、活跃状态和条数过滤运行记录，便于 agent 找到真正需要处理的 run；任务、运行记录和 delivery 列表 API 默认必须有安全条数上限，避免历史数据增长后默认全量返回。
- 支持按任务确认最近一次待确认主运行记录，避免 agent 先查询大量 run 再手动筛选 run_id。
- 运行记录确认或任务归档后，关联的待处理跟进记录必须标记为已取消，默认查询和统计不应把它们视为待处理事项。
- `xushi-skills` 必须明确喝水、起立、伸展、眼休息等健康习惯默认使用 completion anchor，并引导 agent 优先使用全局免打扰策略处理夜间投递，同时记录真实使用中发生的优化反馈草稿。
- 支持查看通知投递历史，包含系统通知成功、失败和 fallback 记录。
- 支持查看 delivery 历史，包含 pending、delayed、digested、delivered、failed、skipped、silenced 和 cancelled 状态。
- 支持在修复 executor token、URL、TLS 或 agent 路由配置后，手动重试仍对应未完成 run 的失败 delivery；重试必须保留原失败 delivery 作为审计历史。
- 支持可选的失败 delivery 自动重试，默认关闭；开启后必须有最大次数限制，并在 retry delivery 结果中保留原失败记录和自动重试次数。
- CI 必须检查应用版本、OpenClaw 插件版本以及内置 plugin/skills 副本一致性，避免发布资产错配。

## 4. v1 任务语义

- 抢购/抢票：固定时间触发，短执行窗口，过期即失败，不补发。
- 饭后吃药：固定或相对时间提醒，允许短暂延迟，需要确认，未确认则跟进。
- 久坐提醒：基于上次确认时间计算下一次提醒，未确认持续跟进。
- 截止任务：可随时开始，截止前完成，逾期后询问是否改期。
- 尽快任务：使用 `asap` 调度，创建后尽快提醒，完成时间模糊，持续温和跟进。
- 模糊事项：先进入待规划池，不强制排期，也不自动触发。
- 会议/时间块：有开始和结束时间，在窗口打开时触发，窗口结束后不再补发。
- 提前准备：绑定主事件，在主事件前提醒准备材料或出门。
- 等待反馈：到指定时间仍无反馈时提醒跟进。
- 习惯/配额：周期内要求完成若干次，支持统计和补做。
- 多阶段任务：一个目标包含多个阶段，每阶段独立提醒和确认。
- 条件触发任务：预留 webhook/agent 回调接口。

## 5. 非目标

- v1 不做云同步、移动端 App、多人协作、账号体系。
- v1 不做完整外部日历双向同步。
- v1 不负责自然语言理解，由接入的 agent 完成理解和结构化转换。

## 6. 需求变更记录

| 日期 | 类型 | 内容 |
| ---- | ---- | ---- |
| 2026-05-09 | 新增 | 创建序时 v1 初始需求，明确 agent 优先、本地 daemon、OpenClaw 插件和日常任务语义。 |
| 2026-05-09 | 明确 | daemon 需要后台自动扫描任务，运行记录需要支持确认完成和未确认跟进闭环。 |
| 2026-05-09 | 新增 | 增加通知投递历史，支持 CLI、API 和 Web 管理台查看。 |
| 2026-05-09 | 明确 | 中国大陆 2026 年节假日和调休数据采用国务院办公厅通知作为来源。 |
| 2026-05-09 | 明确 | OpenClaw executor 从模板占位升级为真实投递探索，后续收敛到 `/hooks/agent`。 |
| 2026-05-09 | 新增 | 增加长任务回调能力，支持 agent 异步提交最终结果。 |
| 2026-05-09 | 新增 | 增加本地配置初始化和诊断命令，改善 OpenClaw 用户安装接入体验。 |
| 2026-05-09 | 明确 | 补充窗口、截止、待规划、完成锚点和工作日顺延的 v1 调度语义。 |
| 2026-05-09 | 新增 | 增加 agent 重试幂等创建、统一错误响应和 asap 尽快任务语义。 |
| 2026-05-09 | 新增 | 增加 PyInstaller 二进制构建脚本和跨平台 GitHub Actions 构建工作流。 |
| 2026-05-09 | 调整 | 中国大陆节假日数据由纯日期数组调整为按节日名称分组，并支持查询调休关联节日。 |
| 2026-05-09 | 新增 | 增加 GitHub 风格 README、MIT License、agent 安装指南和跨平台安装脚本。 |
| 2026-05-09 | 新增 | 增加换行规范和 tag 触发的 GitHub Release 发布工作流。 |
| 2026-05-09 | 新增 | 增加 CONTRIBUTING、SECURITY、Issue 模板和 PR 模板。 |
| 2026-05-09 | 更正 | 修复 reminder 忽略 executor 的投递断点，并明确无 executor 时仅本地通知。 |
| 2026-05-10 | 更正 | 撤回早期 command bridge 方案，避免跨平台和安全边界复杂度。 |
| 2026-05-10 | 调整 | OpenClaw 默认投递链路从 TaskFlow webhook 调整为 `/hooks/agent`，由 agent 处理并投递到聊天渠道。 |
| 2026-05-10 | 调整 | 移除 command executor；通用 webhook executor 暂时仅保留预留位置不实现投递。 |
| 2026-05-10 | 明确 | 完善 OpenClaw `/hooks/agent` 可选字段映射，支持指定 agent、session、channel、recipient、model、fallbacks 和 thinking。 |
| 2026-05-10 | 调整 | OpenClaw HTTPS 自签名证书改为显式 `insecure_tls` 配置，默认保持 HTTP 示例和 TLS 校验。 |
| 2026-05-10 | 调整 | executor 配置从 SQLite/API 保存调整为 `config.json` 管理，OpenClaw 插件仅保留查看工具。 |
| 2026-05-10 | 调整 | 默认本地 API 端口从 `8766` 调整为更高位且保留原记忆点的 `18766`。 |
| 2026-05-10 | 调整 | GitHub Release 流程调整为分离质量检查、Python 包、平台二进制和发布步骤，并生成唯一资产名与校验和。 |
| 2026-05-10 | 新增 | 增加用户手动触发的 CLI 安全升级需求，要求升级前备份配置和 SQLite 数据，并支持 rollback。 |
| 2026-05-10 | 调整 | 安装与升级链路调整为从 GitHub Release 下载二进制，并配置 `xushi` / `xushi-daemon` 为全局命令。 |
| 2026-05-10 | 调整 | Hermes executor 从预留未实现调整为可配置 HTTP agent webhook 投递。 |
| 2026-05-10 | 新增 | 增加 `xushi-skills` agent skill 需求，并要求安装脚本支持经用户授权后的静默安装参数。 |
| 2026-05-10 | 新增 | 增加运行记录过滤、按任务确认最近待确认运行、跟进取消状态和 `xushi-skills` 优化反馈记录要求。 |
| 2026-05-10 | 更正 | 明确安装文档优先适配 OpenClaw 和 Hermes；暂时移除 Codex skill 安装目标，仅保留 OpenClaw/Hermes skills 安装。 |
| 2026-05-10 | 明确 | `xushi-skills` 安装支持 OpenClaw/Hermes 自定义 skills 根目录，兼容 agent 自有目录环境变量。 |
| 2026-05-10 | 调整 | 免打扰从 schedule 层调整为 delivery 层通用策略，支持全局默认、任务覆盖、工作日窗口和摘要聚合。 |
| 2026-05-10 | 明确 | 安装引导必须在安装前强烈推荐并询问是否安装 `xushi-skills`，并在配置完成后通过用户确认的测试提醒验证投递链路。 |
| 2026-05-10 | 明确 | 细化安装后配置流程，要求 agent 重点检查 token 作用域、daemon 重启、executor id、hook URL 可达性和渠道投递结果。 |
| 2026-05-10 | 调整 | `xushi-skills` 从独立 Release zip 调整为随 `xushi` 应用打包，通过 `xushi skills install/status` 安装和检查，不再发布 `xushi-skills.zip`。 |
| 2026-05-10 | 调整 | OpenClaw 插件从独立 Release zip 调整为随 `xushi` 应用打包，通过 `xushi plugins install/status` 安装和检查，并保留 ClawHub 发布入口。 |
| 2026-05-10 | 明确 | 安装诊断需要覆盖 OpenClaw/Hermes token 作用域、TLS URL、agent 路由和修复后失败投递重试。 |
| 2026-05-11 | 明确 | 所有 API 具体时间点必须携带时区偏移，并单独保留 IANA 时区用于 RRULE、免打扰和本地日历判断。 |
| 2026-05-11 | 新增 | 增加显式配置 reload 需求，支持不重启 daemon 更新 executor 和全局免打扰策略。 |
| 2026-05-11 | 调整 | 增加 SQLite 结构化索引与 schema 迁移要求，并明确同一幂等键不同请求体返回冲突。 |
| 2026-05-11 | 新增 | 增加运行期指标、有限自动重试、SQLite PRAGMA 配置、列表默认上限和元数据一致性 CI 要求。 |
| 2026-05-11 | 明确 | `completion` anchor 必须依赖确认时间，禁止从无确认终态运行记录迁移出隐式锚点。 |
| 2026-05-11 | 明确 | 发布二进制必须固定稳定 Python 构建版本并执行启动 smoke test。 |
