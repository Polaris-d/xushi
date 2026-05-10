---
name: xushi-skills
description: Use when an agent needs to install, configure, or operate xushi; turn user reminder, schedule, habit, deadline, follow-up, or automation requests into correct xushi task JSON; choose schedule kinds such as recurring, deadline, window, asap, floating, and one_shot; decide whether completion-based anchoring or confirmation follow-up is needed; ask clarification questions before creating unclear tasks.
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
5. Add `executor_id` only when the user wants delivery through OpenClaw, Hermes, or another configured executor. Otherwise use local notification behavior.
6. Create the task, then keep track of the returned `task.id`.
7. When the user later says the work is done, confirm the relevant run instead of only replying conversationally.

## Reference Map

- Read `references/task-types.md` when choosing a schedule kind or explaining which type fits a real-world request.
- Read `references/schema-patterns.md` when generating concrete task JSON.
- Read `references/clarification-questions.md` when the user's request is underspecified.

## Guardrails

- Do not silently create tasks when the type is ambiguous and a wrong schedule would create real user friction.
- For drinking water, standing up, stretching, eye rest, and similar habits, prefer `anchor: "completion"` because the next reminder should usually be based on the user's actual completion time.
- Keep `max_attempts: 0` only when the user does not want follow-up. In current xushi versions, `0` means "do not follow up", not "unlimited".
- Do not put real tokens in task JSON, examples, docs, or logs. Use environment-variable-backed executor config.
- Treat `floating` as a planning pool item: it does not auto-trigger until a later update gives it a concrete schedule.
