# Reminder Aggregation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable same-minute reminder aggregation while preserving urgent and quiet-policy semantics.

**Architecture:** Keep scheduler responsible for due `Run` creation and put aggregation in the delivery layer. Add a small aggregation policy to settings, group due non-delayed deliveries by action type and executor, and reuse digest delivery mechanics for batched reminders.

**Tech Stack:** Python 3.12, Pydantic models, FastAPI service layer, SQLite-backed delivery records, pytest, ruff, uv build.

---

### Task 1: Document Behavior

**Files:**
- Modify: `docs/PROJECT_REQUIREMENTS.md`
- Modify: `docs/TECHNICAL_DESIGN.md`

- [x] **Step 1: Add requirement text**

Add a requirement that ordinary reminders due in the same minute may be aggregated when the global aggregation policy is enabled, while bypass and expiry-sensitive tasks remain separate.

- [x] **Step 2: Add technical flow**

Add a design note that the delivery layer groups due `pending` deliveries by action type and executor, creates a digest delivery, and marks originals as `digested`.

### Task 2: Write Failing Tests

**Files:**
- Modify: `tests/test_service.py`

- [x] **Step 1: Add same-minute aggregation test**

Create two ordinary one-shot reminders with the same `run_at`, call one `service.tick()`, and assert one digest delivery was delivered while the two original reminders are `digested`.

- [x] **Step 2: Add bypass/expiry test**

Create reminders that should not be aggregated because one uses `quiet_policy.mode="bypass"` or an expiry-sensitive schedule, then assert both are delivered separately.

- [x] **Step 3: Verify red**

Run:

```powershell
uv run pytest tests/test_service.py::test_same_minute_pending_reminders_are_aggregated tests/test_service.py::test_bypass_reminder_is_not_same_minute_aggregated -q
```

Expected: tests fail because pending same-minute aggregation does not exist yet.

### Task 3: Implement Aggregation Policy

**Files:**
- Modify: `src/xushi/models.py`
- Modify: `src/xushi/config.py`
- Modify: `src/xushi/service.py`

- [x] **Step 1: Add model**

Add `ReminderAggregationPolicy` with `enabled`, `window_seconds`, `min_items`, `max_items`, and `include_pending` fields.

- [x] **Step 2: Load settings**

Add `reminder_aggregation` to `Settings`, defaulting to enabled same-minute pending aggregation with a bounded item count.

- [x] **Step 3: Group eligible pending deliveries**

In `process_deliveries`, group `pending` deliveries when their `due_at` values fall into the same configured minute window and are safe to aggregate.

- [x] **Step 4: Reuse digest execution**

Let digest payloads distinguish quiet digest and reminder digest, update original deliveries to `digested`, and keep run audit data intact.

### Task 4: Version and Release Prep

**Files:**
- Modify: `pyproject.toml`
- Modify: `plugins/openclaw-xushi/package.json`
- Modify: `plugins/openclaw-xushi/openclaw.plugin.json`
- Modify: `src/xushi/bundled_plugins/openclaw-xushi/package.json`
- Modify: `src/xushi/bundled_plugins/openclaw-xushi/openclaw.plugin.json`
- Modify: `README.md`
- Modify: `README.en.md`

- [x] **Step 1: Bump version**

Bump the app and bundled plugin metadata to the next available release version because this is a backward-compatible feature addition in the current pre-1.0 release line.

- [x] **Step 2: Update docs**

Mention same-minute aggregation in the feature overview and configuration examples.

### Task 5: Verify and Commit

**Files:**
- All modified files.

- [x] **Step 1: Run targeted tests**

```powershell
uv run pytest tests/test_scheduler.py tests/test_service.py -q
```

- [x] **Step 2: Run full quality checks**

```powershell
uv run pytest
uv run ruff check .
node --check plugins/openclaw-xushi/dist/index.js
uv build --wheel
```

- [x] **Step 3: Commit**

```powershell
git add .
git commit -m "✨ feat(delivery): 添加提醒聚合"
```

Do not push, merge, or create a release tag until the user explicitly approves that remote release step.
