---
name: xushi-skills
description: Use when an agent needs to install, configure, or operate xushi with OpenClaw/Hermes-priority delivery; turn user reminder, schedule, habit, deadline, follow-up, or automation requests into correct xushi task JSON; choose schedule kinds such as recurring, deadline, window, asap, floating, and one_shot; decide whether completion-based anchoring or confirmation follow-up is needed; ask clarification questions before creating unclear tasks; record local optimization notes when real xushi usage exposes issues.
---

# Xushi Skills

## Overview

Use this skill to operate xushi as an agent-facing local scheduler. Prefer it whenever a user asks for reminders, recurring habits, deadlines, follow-ups, local daemon setup, executor delivery, or task confirmation through xushi.

## Time Rules

- Every concrete datetime sent to xushi must include an explicit timezone offset, such as `2026-05-11T09:00:00+08:00` or `2026-05-11T01:00:00Z`. Never send naive datetimes such as `2026-05-11T09:00:00`.
- Always include an IANA `schedule.timezone`, such as `Asia/Shanghai`, for task-local calendar semantics. Offset and timezone are different: the offset identifies an instant; `schedule.timezone` tells xushi how to interpret RRULE wall-clock fields, workday policy, and local user expectations.
- RRULE fields such as `BYHOUR`, `BYMINUTE`, and `BYDAY` are meant to describe the user's local wall-clock rhythm in `schedule.timezone`. For exact wall-clock minute schedules, include `BYSECOND=0` or use examples that have zero seconds.
- Quiet windows use the user's configured quiet-policy timezone. Do not encode sleep or focus windows inside `schedule`; use global or task `quiet_policy`.
- Duration fields such as `expiry`, `grace_period`, and `interval` support day/time ISO durations like `P1D`, `PT10M`, and `P1DT2H`. Do not send months, years, fractions, or negative durations because xushi rejects them.

## Core Workflow

1. Identify the user's scheduling intent before writing JSON.
2. If timing, recurrence, completion semantics, or follow-up behavior is unclear, ask a short clarification question first.
3. Choose the schedule kind and anchor:
   - Fixed calendar rhythm: `recurring` with `anchor: "calendar"`.
   - Habit interval after completion: `recurring` with `anchor: "completion"`.
   - Single exact reminder: `one_shot`.
   - Deadline-based work: `deadline`.
   - Opportunity window: `window`.
   - Immediate reminder: `asap`.
   - Not yet schedulable: `floating`.
4. Decide whether the task requires confirmation. Habits, medicine, chores, and "keep asking me" tasks usually need `requires_confirmation: true`.
5. Prefer a configured OpenClaw or Hermes executor when the user wants agent/chat delivery. Add `executor_id` only when the user wants delivery through OpenClaw, Hermes, or another configured executor. Otherwise use local notification behavior.
6. Create the task, then keep track of the returned `task.id`.
7. When the user later says the work is done, record completion in xushi instead of only replying conversationally. If the task id is known, prefer the task-level complete operation because it also handles early completion before the next reminder exists.
8. If real xushi usage exposes a product issue, confusing behavior, missing guide, or recurring workaround, record a local optimization note. Do not upload or send it unless the user asks.

## Interface Map

- If unsure which integration surface is available, discover capabilities first: OpenClaw plugin `xushi_capabilities`, CLI `xushi capabilities`, or HTTP `GET /api/v1/capabilities`. Raw HTTP agents can also inspect `GET /openapi.json` or `/docs`.
- Create task: plugin `xushi_create_task`; CLI `xushi create <task.json>`; HTTP `POST /api/v1/tasks`.
- List active/pending runs: plugin `xushi_list_runs` with `active_only=true`; CLI `xushi runs --active-only --limit 10`; HTTP `GET /api/v1/runs?active_only=true&limit=10`.
- User says a known task is done: plugin `xushi_complete_task`; CLI `xushi complete <task_id>`; HTTP `POST /api/v1/tasks/{task_id}/complete`. This confirms an existing unfinished primary run, or creates a non-delivered manual completion anchor when a completion-based recurring task is done before the next reminder exists.
- User only needs to confirm the latest pending primary run: plugin `xushi_confirm_latest_run`; CLI `xushi confirm-latest <task_id>`; HTTP `POST /api/v1/tasks/{task_id}/runs/confirm-latest`.
- User says a known run is done: plugin `xushi_confirm_run`; CLI `xushi confirm <run_id>`; HTTP `POST /api/v1/runs/{run_id}/confirm`.
- Manual trigger is only for testing or immediate execution: plugin `xushi_trigger_task`; CLI `xushi trigger <task_id>`; HTTP `POST /api/v1/tasks/{task_id}/runs`. Do not use trigger as a completion confirmation.
- After fixing executor config: plugin `xushi_reload_config` then `xushi_retry_deliveries`; CLI `xushi reload-config` then `xushi retry-deliveries`; HTTP `POST /api/v1/config/reload` then `POST /api/v1/deliveries/retry`.

## Integration Setup Checks

- Before installing agent add-ons, ask the user whether to install the OpenClaw plugin and `xushi-skills`. Strongly recommend yes for OpenClaw/Hermes users, then use installer parameters for non-interactive installation.
- Keep token scopes separate: `XUSHI_API_TOKEN` belongs to the agent/plugin process that calls xushi; `OPENCLAW_HOOKS_TOKEN` and `HERMES_API_TOKEN` belong to the `xushi-daemon` process that calls agent hooks.
- After changing `~/.xushi/config.json` executors, global `quiet_policy`, `reminder_aggregation`, or auto-retry policy, call `xushi_reload_config` from the OpenClaw plugin, run `xushi reload-config`, or `POST /api/v1/config/reload` to refresh the daemon without restarting. Restart `xushi-daemon` for API token, database path, SQLite PRAGMA, host, port, scheduler interval, or daemon-side environment variable changes.
- For OpenClaw TLS, match the URL scheme to the Gateway. HTTPS Gateway needs `https://...`; local self-signed HTTPS also needs `"insecure_tls": true`.
- For OpenClaw routing, set `agent_id` when the reminder must reach a specific working agent. If it is missing, OpenClaw may use its default agent/session.
- After every installation, upgrade, or executor reconfiguration, create one unique smoke-test reminder with `action.executor_id` set, then ask the user whether the target channel received it. Do not call install or upgrade complete until the user confirms receipt.
- After upgrading, sync bundled plugin/skills when they were installed before, restart or reload the daemon as needed, then run the same smoke test because the binary, plugin, skills, daemon process, and executor config must still match.
- If a delivery failed before the configuration was fixed, reload config or restart as needed, then use `xushi_retry_deliveries` from the OpenClaw plugin or `xushi retry-deliveries` from the shell.
- Use `GET /api/v1/metrics` when you need to confirm the daemon is ticking, creating runs, delivering notifications, or retrying failures. Remember metrics are in-memory and reset when the daemon restarts.

## Reference Map

- Read `references/task-types.md` when choosing a schedule kind or explaining which type fits a real-world request.
- Read `references/schema-patterns.md` when generating concrete task JSON.
- Read `references/clarification-questions.md` when the user's request is underspecified.
- Read `references/optimization-notes.md` when recording real usage issues or feedback drafts.

## Guardrails

- Do not silently create tasks when the type is ambiguous and a wrong schedule would create real user friction.
- Never omit timezone offsets from `run_at`, `deadline`, `window_start`, `window_end`, callback `finished_at`, or other concrete time fields. xushi rejects naive datetimes because the daemon cannot safely guess the user's timezone.
- Prefer OpenClaw and Hermes integration paths when configuring agent delivery. Use the OpenClaw plugin and `/hooks/agent` executor or the Hermes agent webhook when they are available.
- For drinking water, standing up, stretching, eye rest, and similar habits, default to `recurring` with `anchor: "completion"` and `requires_confirmation: true` because the next reminder should usually be based on the user's actual completion time.
- If the user completes one of those habits before the next reminder has fired, call the task-level complete operation. Do not trigger the task just to create something to confirm.
- For night disturbance, prefer the user's global `quiet_policy`. New tasks inherit it by default; only set task `quiet_policy.mode` to `override` or `bypass` when the user clearly wants task-specific behavior.
- Use `anchor: "calendar"` for health habits only when the user explicitly wants fixed wall-clock slots.
- Keep `max_attempts: 0` only when the user does not want follow-up. In current xushi versions, `0` means "do not follow up", not "unlimited".
- Keep list queries bounded. xushi API defaults task/run/delivery lists to 100 items; pass an explicit `limit` only when you need a larger bounded window.
- Do not put real tokens in task JSON, examples, docs, or logs. Use environment-variable-backed executor config.
- Treat `floating` as a planning pool item: it does not auto-trigger until a later update gives it a concrete schedule.
