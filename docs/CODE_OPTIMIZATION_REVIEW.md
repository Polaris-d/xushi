# xushi 代码优化复盘（从整体到细节）

> 目标：先校准“方向正确性”，再按层次拆解可优化点，避免陷入局部微优化。

## 0. 总体结论（先看方向）

当前代码库在产品方向上是清晰且一致的：**本地优先 + agent first + 可审计调度闭环**。优先级排序（可靠触发、可追踪投递、确认闭环）是正确的。

但从工程角度看，系统已经进入“可用之后的第二阶段”：

1. **性能与规模边界**需要补齐（当前更多是正确性优先实现）。
2. **领域逻辑聚合度**需要提升（service 层职责偏重）。
3. **可运维性/可观察性**可以从“日志可看”升级到“指标可控”。
4. **数据层演进策略**应从全 JSON payload 逐步走向“关键字段结构化索引”。

---

## 1. 架构与边界（宏观）

### 1.1 Service 层过重，建议拆分应用服务

**现状**
- `XushiService` 同时承担任务 CRUD、调度 tick、投递编排、确认链路、跟进链路、重试与聚合等职责，方法较多，跨越多个子域。  

**风险**
- 变更影响面大，回归成本上升。
- 新功能很容易继续“堆到 service”，导致复杂度持续攀升。

**建议**
- 拆分为更明确的应用服务（例如）：
  - `TaskApplicationService`
  - `RunLifecycleService`
  - `DeliveryOrchestrator`
  - `FollowUpService`
- `XushiService` 只保留 Facade 编排。

**优先级**：高（P1）。

### 1.2 调度与投递的边界已正确，但接口契约可再前移

**现状**
- 设计文档已经明确 scheduler 只算“到期”，delivery 负责 quiet policy / digest，方向正确。  

**建议**
- 在代码层进一步显式化“状态机转换表”（run_status 与 delivery_status 的合法转换），避免隐式 if/else 累积。
- 新增 `domain/policies.py` 或 `state_machine.py` 抽离状态迁移规则。

**优先级**：中高（P1-P2）。

---

## 2. 数据层与性能（中观）

### 2.1 SQLite 频繁全量扫描，建议补“关键查询索引 + 条件查询”

**现状**
- `list_runs()`、`list_deliveries()`、`list_tasks()` 常用后在内存再过滤。  
- `confirm_latest_run()` 先 `list_runs()` 再筛选 task + status。  

**风险**
- 任务/运行记录增长后，tick 与确认操作会线性退化。

**建议（短期）**
- 增加专用查询接口：
  - `list_pending_runs_by_task(task_id, limit=1)`
  - `list_due_deliveries(now)`
  - `list_active_tasks()`
- 新增索引：
  - `runs(task_id, status, scheduled_for DESC)`
  - `deliveries(status, deliver_at)`
  - `tasks(status, created_at DESC)`

**建议（中期）**
- 保留 payload JSON，但把常查询字段“冗余成列”并索引（当前已做一部分，可继续扩展）。

**优先级**：高（P1）。

### 2.2 连接模型可继续优化

**现状**
- 每次操作短连接打开/关闭，优点是句柄安全。

**建议**
- 保持短连接策略不变（兼容性优先），但可增加：
  - `PRAGMA journal_mode=WAL`（可配置启用）
  - `PRAGMA synchronous=NORMAL`（在文档中声明一致性权衡）
- 对只读批量查询加轻量缓存（tick 周期内）。

**优先级**：中（P2）。

---

## 3. 领域逻辑正确性与可维护性（中观）

### 3.1 ISO duration 解析能力偏窄

**现状**
- `parse_iso_duration` 仅支持 `PT` 级 H/M/S 组合，不支持天、负值、小数等。

**风险**
- 与用户/agent 预期 ISO-8601 不一致，容易出现“看似合法但不支持”的输入摩擦。

**建议**
- 明确策略二选一：
  1) 文档中继续强约束“仅 PT-HMS”；
  2) 引入成熟 duration 解析库或扩展 parser 支持 `P1D`。
- 同步补充边界测试（非法字符、空值、超大值、组合值）。

**优先级**：中高（P1-P2）。

### 3.2 状态变更代码路径有重复，建议模板化

**现状**
- `confirm_run` 与 `callback_run` 中存在相似的“成功后确认 origin + 取消 follow-ups + 取消 deliveries”分支。

**风险**
- 重复逻辑后续容易出现行为漂移（一个分支修了，另一个漏修）。

**建议**
- 提炼私有方法：
  - `_mark_run_succeeded(run, at, source)`
  - `_propagate_origin_confirmation(...)`
  - `_cancel_related_followups(...)`
- 用单元测试覆盖“主 run / 跟进 run / callback 成功”三种路径一致性。

**优先级**：高（P1）。

---

## 4. 可测试性与质量门禁（中观）

### 4.1 已有测试广度不错，建议补“性能与回归契约测试”

**现状**
- 测试文件覆盖模块较全（API、scheduler、storage、service 等）。

**建议**
- 新增 3 类测试：
  1) **状态机契约测试**：给定输入状态只允许合法迁移。
  2) **规模回归测试**：构造 1k/10k runs 的 `confirm_latest` 与 `tick` 时延阈值。
  3) **幂等冲突测试**：并发同 idempotency_key 创建任务的行为一致性。

**优先级**：中高（P2）。

### 4.2 静态质量工具可升级

**建议**
- 在 CI 增加 `mypy`（或 pyright）作为可选门禁阶段。
- 对复杂函数设置 Ruff 的复杂度阈值（C901）并逐步收敛。

**优先级**：中（P3）。

---

## 5. 可观测性与运维（中观）

### 5.1 从日志走向指标

**现状**
- 有调度日志与投递路径，但指标体系不完整。

**建议**
- 增加基础指标（可先内存计数 + API 输出，后续再接 Prometheus）：
  - `runs_created_total`
  - `deliveries_succeeded_total / failed_total / delayed_total`
  - `follow_up_created_total`
  - `tick_duration_ms`
- 在 `doctor` 中增加“最近 N 次 tick 摘要”。

**优先级**：中（P2）。

### 5.2 失败重试策略可更细化

**建议**
- 当前是手动 retry，方向稳妥；可增加“可选限次自动重试（默认关）”。
- 对可恢复错误（超时/5xx）与不可恢复错误（配置缺失/4xx）区分策略。

**优先级**：中（P2）。

---

## 6. API 与契约演进（细节）

### 6.1 统一响应结构已做，建议补错误码语义分层

**建议**
- 明确业务错误码段（如 42xxx 调度、43xxx executor、44xxx 配置）。
- 使 agent 能基于 code 做自动恢复提示，而不是仅看 message。

### 6.2 幂等键策略建议文档化 TTL 与冲突域

**建议**
- 明确 `idempotency_key` 的唯一域（全局 / 每 task 类型 / 每调用方）。
- 可选记录首次请求哈希，冲突时返回“同 key 但请求体不同”诊断。

---

## 7. 安全与配置（细节）

### 7.1 本地 token 与 webhook token 的误配风险仍高

**建议**
- 在 `doctor` 中给出更强的“修复指令模板”（逐行 shell/PowerShell）。
- 对 insecure TLS 打开场景输出更显眼警告（含建议关闭条件）。

### 7.2 配置热更新（可选）

**建议**
- 目前变更 executor 需重启 daemon，简单可靠。
- 后续可增加 `SIGHUP` / API 触发 reload（默认仍建议重启），平衡可用性。

---

## 8. 文档与开发体验（细节）

### 8.1 版本一致性约束可自动化

**现状**
- 文档明确 `pyproject`、plugin 元数据需版本一致。

**建议**
- 增加 CI 脚本自动校验这些文件版本号一致，失败即阻断。

### 8.2 “设计文档 vs 代码”一致性巡检

**建议**
- 每次 release 前运行一份 checklist（端口默认值、支持 executor 列表、API 列表、安装参数）。
- 避免文档先行后代码漂移。

---

## 9. 建议落地路线图（执行顺序）

### Phase 1（1~2 周，先保收益）
1. 为 runs/deliveries/tasks 增索引与专用查询接口。  
2. 抽取 run 确认/回调重复逻辑。  
3. 新增状态机契约测试。  

### Phase 2（2~4 周，稳健扩展）
1. 拆分 `XushiService` 为多个应用服务。  
2. 增加基础运行指标与 tick 统计。  
3. 完善 duration 策略（扩展或显式限制）。  

### Phase 3（持续优化）
1. 关键路径性能基准与回归门禁。  
2. 配置 reload 与更细粒度重试策略。  
3. CI 增加版本一致性/文档一致性自动检查。  

---

## 10. 最后建议（决策原则）

- **先做不会改变业务语义但显著降风险的改动**：索引、查询下推、重复逻辑抽取、测试补齐。  
- **再做结构调整**：服务拆分与状态机显式化。  
- **最后做体验增强**：指标、热更新、自动恢复策略。  

这样可以保证“整体方向不偏”，并且每一步都可独立验收、可回滚、可度量。
