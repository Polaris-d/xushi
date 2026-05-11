# Xushi Schema Patterns

Use these patterns as starting points. Always adapt timezone, time, executor, and follow-up behavior to the user's actual request.

Hard time rules:

- Concrete datetime fields must include an offset (`Z`, `+08:00`, etc.). Do not send naive values like `2026-05-10T09:00:00`.
- `schedule.timezone` must be an IANA timezone such as `Asia/Shanghai`. xushi uses it to interpret RRULE wall-clock fields, workday policy, and task-local calendar behavior.
- Quiet policy has its own timezone for delivery behavior. Use it for sleep/focus windows instead of changing schedule semantics.

## Completion-Based Habit

Good for drinking water, standing up, stretching, eye rest, and similar tasks.

```json
{
  "title": "喝水",
  "schedule": {
    "kind": "recurring",
    "run_at": "2026-05-10T09:00:00+08:00",
    "rrule": "FREQ=HOURLY;INTERVAL=2",
    "timezone": "Asia/Shanghai",
    "anchor": "completion",
    "missed_policy": "catch_up_latest"
  },
  "action": {
    "type": "reminder",
    "executor_id": "openclaw",
    "payload": {
      "message": "该喝水了"
    }
  },
  "follow_up_policy": {
    "requires_confirmation": true,
    "grace_period": "PT10M",
    "interval": "PT10M",
    "max_attempts": 3,
    "ask_reschedule_on_timeout": true
  },
  "created_by": "agent"
}
```

Key points:

- Use `anchor: "completion"` when the next reminder should reset after confirmation.
- Let normal tasks inherit the user's global `quiet_policy` for night-time delay and digest aggregation.
- Keep `requires_confirmation: true`.
- In current xushi versions, `max_attempts: 0` disables follow-up.
- If the user says they completed the habit, confirm the latest pending run for that task. Do not only reply in chat.

Common wrong pattern:

```json
{
  "title": "喝水",
  "schedule": {
    "kind": "recurring",
    "rrule": "FREQ=HOURLY;INTERVAL=2",
    "timezone": "Asia/Shanghai",
    "anchor": "calendar"
  },
  "follow_up_policy": {
    "requires_confirmation": false,
    "max_attempts": 0
  }
}
```

This is wrong for most "每 2 小时喝水" requests because the reminder does not reset after the user actually drinks water, and xushi receives no completion signal.

## Global Quiet Policy

Use this in `~/.xushi/config.json` when the user wants default do-not-disturb behavior for all tasks:

```json
{
  "quiet_policy": {
    "enabled": true,
    "timezone": "Asia/Shanghai",
    "windows": [
      {"start": "12:30", "end": "14:00", "days": "workdays"},
      {"start": "22:30", "end": "08:00", "days": "everyday"}
    ],
    "behavior": "delay",
    "aggregation": {"enabled": true, "mode": "digest", "max_items": 10}
  }
}
```

Task-level override for an explicit night reminder:

```json
{
  "title": "凌晨赶飞机",
  "quiet_policy": {"mode": "bypass"}
}
```

## Fixed Calendar Recurrence

Good for fixed medicine times, weekly meetings, rent, daily reports, and other wall-clock rhythms.

```json
{
  "title": "早饭后吃药",
  "schedule": {
    "kind": "recurring",
    "run_at": "2026-05-10T08:15:00+08:00",
    "rrule": "FREQ=DAILY;BYHOUR=8;BYMINUTE=15;BYSECOND=0",
    "timezone": "Asia/Shanghai",
    "anchor": "calendar",
    "missed_policy": "catch_up_latest"
  },
  "action": {
    "type": "reminder",
    "executor_id": "openclaw",
    "payload": {
      "message": "早饭后吃药"
    }
  },
  "follow_up_policy": {
    "requires_confirmation": true,
    "grace_period": "PT15M",
    "interval": "PT15M",
    "max_attempts": 3
  },
  "created_by": "agent"
}
```

## One-Shot Reminder

```json
{
  "title": "给张三打电话",
  "schedule": {
    "kind": "one_shot",
    "run_at": "2026-05-10T15:30:00+08:00",
    "timezone": "Asia/Shanghai",
    "missed_policy": "catch_up_latest"
  },
  "action": {
    "type": "reminder",
    "payload": {
      "message": "给张三打电话"
    }
  },
  "created_by": "agent"
}
```

## Deadline Task

```json
{
  "title": "提交报销材料",
  "schedule": {
    "kind": "deadline",
    "deadline": "2026-05-15T18:00:00+08:00",
    "timezone": "Asia/Shanghai",
    "missed_policy": "catch_up_latest"
  },
  "action": {
    "type": "reminder",
    "payload": {
      "message": "报销材料今天截止，请确认是否已经提交"
    }
  },
  "follow_up_policy": {
    "requires_confirmation": true,
    "grace_period": "PT0S",
    "interval": "PT30M",
    "max_attempts": 3,
    "ask_reschedule_on_timeout": true
  },
  "created_by": "agent"
}
```

## Window Task

```json
{
  "title": "午休散步",
  "schedule": {
    "kind": "window",
    "window_start": "2026-05-10T12:00:00+08:00",
    "window_end": "2026-05-10T13:00:00+08:00",
    "timezone": "Asia/Shanghai",
    "expiry": "PT1H"
  },
  "action": {
    "type": "reminder",
    "payload": {
      "message": "午休时间到了，可以出去走走"
    }
  },
  "created_by": "agent"
}
```

## Floating Planning Item

```json
{
  "title": "安排体检",
  "schedule": {
    "kind": "floating",
    "timezone": "Asia/Shanghai"
  },
  "action": {
    "type": "reminder",
    "payload": {
      "message": "安排体检"
    }
  },
  "created_by": "agent"
}
```

Floating tasks do not auto-trigger. Prefer asking the user for a concrete time if they expect an actual reminder.
