# 序时 xushi 项目需求文档

## 1. 项目定位

序时是 AI agent 优先的本地化日程管理与排期工具。第一阶段重点服务 OpenClaw、Hermes 等 agent 工具，提供可靠的本地调度、提醒、补偿、跟进和任务审计能力。

## 2. 目标用户

- 已使用 OpenClaw、Hermes 等 agent 工具的个人用户。
- 需要本地可靠提醒、循环任务和 agent 定时执行能力的开发者。
- 希望通过开源工具管理个人工作生活排期的高级用户。

## 3. v1 核心需求

- 独立 `xushi-daemon` 常驻进程负责调度，不依赖 agent 自身常驻。
- 默认只监听 `127.0.0.1:18766`，通过本地 token 鉴权。
- 支持结构化任务输入，由 agent 将自然语言转换为序时 schema。
- 支持固定时间、循环任务、时间窗口、截止时间、持续时长、过期策略、完成确认和未完成跟进。
- 支持 `idempotency_key`，保障 agent 重试创建任务时不会重复生成任务。
- API 成功和错误响应均使用统一 JSON 结构，方便 agent 稳定解析。
- 支持 ISO 8601 时间、RRULE、timezone。
- 支持中国大陆工作日、法定节假日和调休判断；节假日与调休数据必须标注关联节日名称；工作日策略下可将触发时间顺延到下一个中国大陆工作日。
- 支持基于完成确认时间重新计算下一次提醒，适配久坐提醒等 completion anchor 场景。
- 支持“至少触发一次”的可靠性语义。
- 错过触发时默认只补偿最近一次。
- 每次触发生成可审计运行记录。
- agent/聊天渠道优先通知：提醒任务配置 `executor_id` 时必须通过对应 executor 投递；未配置 executor 的 reminder 仅使用本地系统通知和 Web 管理台记录。
- 内置 OpenClaw、Hermes、webhook executor 概念。
- executor 配置必须存放在本地 `config.json` 的 `executors` 数组中，数据库不保存 executor 配置。
- OpenClaw executor 默认使用 `mode=hooks_agent` 调用 OpenClaw `/hooks/agent`，让 OpenClaw agent 处理提醒文本并通过 `deliver=true` 投递到聊天渠道。
- OpenClaw executor 必须支持 `token_env`，避免把 OpenClaw hook token 写入任务或 executor JSON。
- OpenClaw executor 必须支持 `/hooks/agent` 的可选字段：`name`、`agent_id`、`wake_mode`、`deliver`、`channel`、`to`、`model`、`fallbacks`、`thinking`、`timeout_seconds`。
- OpenClaw executor 必须暴露 `insecure_tls` 配置项；默认保持 TLS 证书校验，仅在用户显式配置本机自签名 HTTPS 时关闭校验。
- Hermes 和通用 webhook executor v1 仅保留 schema 位置，调用时返回明确未实现状态。
- v1 暂不提供 command executor，避免跨平台 shell、命令注入和环境差异扩大配置复杂度。
- OpenClaw 插件必须提供执行器查看工具；executor 写入由本地 `config.json` 管理，不通过 API 或插件保存。
- 长任务支持执行器异步回调最终结果，更新运行记录成功或失败状态。
- 提供 CLI 和本地 Web 管理台。
- 提供 OpenClaw TypeScript 原生插件。
- 提供本地配置初始化命令，生成本地 token、SQLite 路径和 daemon 端口配置，便于 OpenClaw 插件和用户共享同一连接信息。
- 提供诊断命令，检查配置文件、数据库目录和监听端口，帮助用户定位 daemon 跑不起来的问题。
- 提供面向人类复制给 LLM Agent 的安装提示词和 agent 可读安装指南。
- 提供 Windows PowerShell 与 macOS/Linux shell 安装脚本，默认安装到用户本地目录。
- 提供 wheel 和跨平台预编译二进制构建配置，降低非 Python 用户安装门槛。
- 提供 tag 触发的 GitHub Release 工作流，发布 wheel 与跨平台二进制产物。
- GitHub Release 资产必须使用唯一、可读的平台命名，并包含 OpenClaw 插件包、自动 release notes 和 SHA256 校验和。
- 提供 `.gitattributes` 控制跨平台换行，避免 shell 脚本和 CI 配置在 Windows 开发环境中被破坏。
- 项目采用 MIT License 开源。
- 提供贡献指南、安全策略、Issue 模板和 PR 模板，降低外部协作成本。
- daemon 启动后必须自动扫描到期任务和未确认跟进，不能依赖用户手动执行 `tick`。
- 支持确认运行记录已完成，确认后停止后续跟进提醒。
- 支持查看通知投递历史，包含系统通知成功、失败和 fallback 记录。

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
| 2026-05-10 | 调整 | 移除 command executor；Hermes 和通用 webhook executor 暂时仅保留预留位置不实现投递。 |
| 2026-05-10 | 明确 | 完善 OpenClaw `/hooks/agent` 可选字段映射，支持指定 agent、session、channel、recipient、model、fallbacks 和 thinking。 |
| 2026-05-10 | 调整 | OpenClaw HTTPS 自签名证书改为显式 `insecure_tls` 配置，默认保持 HTTP 示例和 TLS 校验。 |
| 2026-05-10 | 调整 | executor 配置从 SQLite/API 保存调整为 `config.json` 管理，OpenClaw 插件仅保留查看工具。 |
| 2026-05-10 | 调整 | 默认本地 API 端口从 `8766` 调整为更高位且保留原记忆点的 `18766`。 |
| 2026-05-10 | 调整 | GitHub Release 流程调整为分离质量检查、Python 包、平台二进制和发布步骤，并生成唯一资产名与校验和。 |
