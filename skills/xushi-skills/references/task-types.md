# Xushi Task Types

Use this guide to map real user requests to xushi schedule kinds. The important part is not the words the user uses, but the time semantics behind the request.

## Quick Decision Table

| User intent | Schedule kind | Typical anchor | Confirmation |
| --- | --- | --- | --- |
| One exact future reminder | `one_shot` | n/a | Optional |
| Repeated fixed calendar rhythm | `recurring` | `calendar` | Optional or required |
| Repeated habit after completion | `recurring` | `completion` | Required |
| Work due by a final time | `deadline` | n/a | Usually required |
| Reminder inside an available time range | `window` | n/a | Optional |
| Remind as soon as possible | `asap` | n/a | Optional |
| Unspecific "someday / when free" item | `floating` | n/a | Not auto-triggered |

## Recurring With Completion Anchor

Use `recurring` with `anchor: "completion"` when the next reminder should be calculated from the user's actual completion time. This is the best fit for interval habits where delays should shift the next occurrence.

Examples:

- "每 2 小时提醒我喝水。"
  - The user cares about time since last drink, not a fixed wall-clock slot.
  - If they confirm at 10:20, the next reminder should be around 12:20.
  - Use `requires_confirmation: true`, otherwise xushi cannot know the completion time.
- "每小时提醒我起立活动。"
  - The healthy interval starts after the user actually stands up.
  - A late confirmation should push the next reminder later.
- "每 45 分钟提醒我休息眼睛。"
  - The user's eyes need rest after a continuous work interval.
  - The next timer should reset when the user confirms the break.
- "每 3 小时提醒我给猫换水。"
  - The maintenance interval is based on actual completion.
  - If the user does it early, the next reminder should move earlier from that completion time.
- "每 30 分钟提醒我检查一下锅。"
  - The next check should be based on the last confirmed check.
  - Confirmation is important for safety-sensitive repeated checks.

Ask if unclear:

- "这个循环是按固定整点来，还是从你确认完成后重新计时？"
- "如果你没有确认，我要追问几次？"

## Recurring With Calendar Anchor

Use `recurring` with `anchor: "calendar"` when the schedule belongs to a fixed calendar rhythm. Completion time does not move the next occurrence.

Examples:

- "每天早上 8 点提醒我吃药。"
  - The medicine time is fixed.
  - If the user confirms at 8:30, tomorrow is still 8:00.
- "每周一 9 点提醒我开周会。"
  - The event is tied to weekday and wall-clock time.
  - Completion confirmation should not change the meeting schedule.
- "每月 1 号提醒我交房租。"
  - The date is fixed by a calendar rule.
  - Use monthly RRULE.
- "工作日 18:00 提醒我写日报。"
  - The trigger follows workday calendar policy and fixed time.
  - Completion is useful for recordkeeping but should not shift the next workday reminder.
- "每晚 22:30 提醒我睡前复盘。"
  - The user wants a stable evening routine slot.
  - Late completion should not shift the next day's evening reminder.

Ask if unclear:

- "这是固定在每天/每周的时间点，还是完成后隔一段时间再提醒？"

## One-Shot

Use `one_shot` for a single reminder at a specific date and time. It should not repeat.

Examples:

- "今天 15:30 提醒我给张三打电话。"
  - Exact single time, no recurrence.
- "明早 9 点提醒我拿快递。"
  - One future reminder.
- "今晚 20:00 提醒我看直播。"
  - Event happens once.
- "5 月 12 日 10 点提醒我去医院。"
  - A concrete appointment reminder.
- "下午会议前 10 分钟提醒我打开材料。"
  - If the meeting time is known, this can be one exact reminder.

Ask if unclear:

- "这只是提醒一次，还是以后也要重复？"

## Deadline

Use `deadline` when the user cares about finishing something before a final time. It represents a due point, not necessarily the start time.

Examples:

- "周五前提醒我提交报销材料。"
  - The important boundary is the final due date.
- "月底前提醒我交税。"
  - The task can be done earlier; the deadline is the last acceptable time.
- "下周三之前帮我订机票。"
  - There is a latest completion time, not a fixed meeting.
- "护照到期前一个月提醒我续签。"
  - The trigger is derived from a due date.
- "今晚 23:00 前提醒我交作业。"
  - The work is due by a deadline.

Ask if unclear:

- "你希望在截止点提醒，还是提前多久开始提醒？"
- "如果到期还没完成，要不要继续追问或询问改期？"

## Window

Use `window` when a reminder is only meaningful inside a time range. The start and end both matter.

Examples:

- "12:00 到 13:00 午休期间提醒我出去走走。"
  - The reminder is useful only within lunch break.
- "14:00 到 18:00 快递可能到，提醒我留意电话。"
  - There is an opportunity window.
- "抢票 10:00 开始，10:05 结束，窗口内提醒我。"
  - The task expires quickly after the window.
- "会议开始前 30 分钟到开始时之间提醒我准备材料。"
  - Preparation has a bounded window.
- "晚上 19:00 到 21:00 之间提醒我洗衣服。"
  - The user provided a valid time range rather than an exact point.

Ask if unclear:

- "这个提醒过了这个时间段还要补发吗？"
- "窗口开始时提醒一次，还是窗口内持续追问？"

## ASAP

Use `asap` when the user asks for an immediate or near-immediate reminder without a specific future time.

Examples:

- "尽快提醒我回邮件。"
  - The user wants prompt action.
- "现在有空就提醒我发消息。"
  - Trigger soon after creation.
- "daemon 启动后马上提醒我检查任务列表。"
  - Creation/daemon time is the anchor.
- "立刻提醒我喝水。"
  - Immediate reminder, not a recurring habit unless the user adds a frequency.
- "等一下就提醒我保存文件。"
  - If "等一下" is not a concrete duration, ask; if they mean soon, use `asap`.

Ask if unclear:

- "你是要马上提醒一次，还是要建立一个长期循环？"

## Floating

Use `floating` when the user has an intention but no actionable time. It will not auto-trigger until updated with a real schedule.

Examples:

- "有空安排一次体检。"
  - There is no trigger time.
  - Agent should ask follow-up questions or keep it as planning.
- "以后找时间整理照片。"
  - No deadline or recurrence.
- "某天帮我规划一下学习路线。"
  - The task needs later scheduling.
- "有时间提醒我研究一下保险。"
  - "有时间" is not enough for reliable scheduling.
- "找个合适时间约朋友吃饭。"
  - Needs date/time negotiation first.

Ask if unclear:

- "这是先放进待规划池，还是你想给它一个具体提醒时间？"
