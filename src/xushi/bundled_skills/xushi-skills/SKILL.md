---
name: xushi-skills
description: Use when an agent needs to install, configure, or operate xushi with OpenClaw/Hermes-priority delivery; turn user reminder, schedule, habit, deadline, follow-up, or automation requests into correct xushi task JSON; choose schedule kinds such as recurring, deadline, window, asap, floating, and one_shot; decide whether completion-based anchoring or confirmation follow-up is needed; ask clarification questions before creating unclear tasks; record local optimization notes when real xushi usage exposes issues.
---

# Xushi Skills

## Overview

Use this skill to operate xushi as an agent-facing local scheduler. Prefer it whenever a user asks for reminders, recurring habits, deadlines, follow-ups, local daemon setup, executor delivery, or task confirmation through xushi.

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
7. When the user later says the work is done, confirm the relevant run instead of only replying conversationally. If the task id is known, prefer confirming the latest pending run for that task before listing all runs.
8. If real xushi usage exposes a product issue, confusing behavior, missing guide, or recurring workaround, record a local optimization note. Do not upload or send it unless the user asks.

## Reference Map

- Read `references/task-types.md` when choosing a schedule kind or explaining which type fits a real-world request.
- Read `references/schema-patterns.md` when generating concrete task JSON.
- Read `references/clarification-questions.md` when the user's request is underspecified.
- Read `references/optimization-notes.md` when recording real usage issues or feedback drafts.

## Guardrails

- Do not silently create tasks when the type is ambiguous and a wrong schedule would create real user friction.
- Prefer OpenClaw and Hermes integration paths when configuring agent delivery. Use the OpenClaw plugin and `/hooks/agent` executor or the Hermes agent webhook when they are available.
- For drinking water, standing up, stretching, eye rest, and similar habits, default to `recurring` with `anchor: "completion"` and `requires_confirmation: true` because the next reminder should usually be based on the user's actual completion time.
- For night disturbance, prefer the user's global `quiet_policy`. New tasks inherit it by default; only set task `quiet_policy.mode` to `override` or `bypass` when the user clearly wants task-specific behavior.
- Use `anchor: "calendar"` for health habits only when the user explicitly wants fixed wall-clock slots.
- Keep `max_attempts: 0` only when the user does not want follow-up. In current xushi versions, `0` means "do not follow up", not "unlimited".
- Do not put real tokens in task JSON, examples, docs, or logs. Use environment-variable-backed executor config.
- Treat `floating` as a planning pool item: it does not auto-trigger until a later update gives it a concrete schedule.
