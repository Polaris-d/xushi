# Xushi Schema Patterns

Use these patterns as starting points. Always adapt timezone, time, executor, and follow-up behavior to the user's actual request.

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
- Keep `requires_confirmation: true`.
- In current xushi versions, `max_attempts: 0` disables follow-up.

## Fixed Calendar Recurrence

Good for fixed medicine times, weekly meetings, rent, daily reports, and other wall-clock rhythms.

```json
{
  "title": "早饭后吃药",
  "schedule": {
    "kind": "recurring",
    "run_at": "2026-05-10T08:15:00+08:00",
    "rrule": "FREQ=DAILY",
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
