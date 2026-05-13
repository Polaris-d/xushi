"""提醒投递策略与免打扰窗口。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from xushi.calendar import ChinaWorkdayCalendar
from xushi.models import QuietAggregation, QuietPolicy, QuietWindow, Task, parse_clock_minutes
from xushi.timezone import get_tzinfo


@dataclass(frozen=True)
class DeliveryPlan:
    """一次投递的计划结果。"""

    status: str
    deliver_at: datetime
    reason: str | None = None


class QuietPolicyEngine:
    """根据全局和任务级策略计算投递时间。"""

    def __init__(
        self,
        global_policy: QuietPolicy | None = None,
        calendar: ChinaWorkdayCalendar | None = None,
    ) -> None:
        self.global_policy = global_policy or QuietPolicy()
        self.calendar = calendar or ChinaWorkdayCalendar()

    def plan(self, task: Task, due_at: datetime) -> DeliveryPlan:
        """计算任务到期后的投递计划。"""
        policy = self.effective_policy(task)
        if not policy.enabled or not policy.windows or policy.behavior == "bypass":
            return DeliveryPlan(status="pending", deliver_at=due_at)

        delayed_until = self.next_allowed_at(due_at, policy)
        if delayed_until == self._as_policy_time(due_at, policy):
            return DeliveryPlan(status="pending", deliver_at=due_at)

        if policy.behavior == "delay":
            return DeliveryPlan(status="delayed", deliver_at=delayed_until, reason="quiet_window")
        if policy.behavior == "skip":
            return DeliveryPlan(status="skipped", deliver_at=due_at, reason="quiet_window")
        if policy.behavior == "silent":
            return DeliveryPlan(status="silenced", deliver_at=due_at, reason="quiet_window")
        return DeliveryPlan(status="pending", deliver_at=due_at)

    def effective_policy(self, task: Task) -> QuietPolicy:
        """合并全局免打扰和任务级策略。"""
        task_policy = task.quiet_policy
        if task_policy.mode == "bypass":
            return QuietPolicy(enabled=True, behavior="bypass", windows=[])

        if task_policy.mode == "override":
            return QuietPolicy(
                enabled=True,
                timezone=task_policy.timezone or task.schedule.timezone,
                windows=task_policy.windows,
                behavior=task_policy.behavior or "delay",
                aggregation=task_policy.aggregation or QuietAggregation(),
            )

        base = self.global_policy
        if task_policy.mode in {"skip", "silent"}:
            return QuietPolicy(
                enabled=base.enabled or bool(task_policy.windows),
                timezone=task_policy.timezone or base.timezone or task.schedule.timezone,
                windows=task_policy.windows or base.windows,
                behavior=task_policy.mode,
                aggregation=task_policy.aggregation or base.aggregation,
            )
        return base

    def should_aggregate(self, task: Task) -> bool:
        """判断任务延迟投递是否参与摘要聚合。"""
        policy = self.effective_policy(task)
        return policy.enabled and policy.behavior == "delay" and policy.aggregation.enabled

    def next_allowed_at(self, value: datetime, policy: QuietPolicy) -> datetime:
        """返回不在免打扰窗口内的最早时间。"""
        current = self._as_policy_time(value, policy)
        for _ in range(20):
            containing = self._containing_window(current, policy)
            if containing is None:
                return current
            current = self._window_end_at(current, containing)
        return current

    def _as_policy_time(self, value: datetime, policy: QuietPolicy) -> datetime:
        zone = get_tzinfo(policy.timezone)
        if value.tzinfo is None:
            return value.replace(tzinfo=zone)
        return value.astimezone(zone)

    def _containing_window(
        self,
        value: datetime,
        policy: QuietPolicy,
    ) -> QuietWindow | None:
        minute = value.hour * 60 + value.minute
        for window in policy.windows:
            start = window.start_minutes()
            end = window.end_minutes()
            if start < end:
                window_date = value.date()
                in_window = start <= minute < end
            else:
                window_date = value.date() - timedelta(days=1) if minute < end else value.date()
                in_window = minute >= start or minute < end
            if in_window and self._applies_on(window, window_date):
                return window
        return None

    def _applies_on(self, window: QuietWindow, value: date) -> bool:
        if window.days == "everyday":
            return True
        if window.days == "weekdays":
            return value.weekday() < 5
        is_workday = self.calendar.is_workday(value)
        if window.days == "workdays":
            return is_workday
        if window.days == "weekends":
            return not is_workday
        return False

    def _window_end_at(self, value: datetime, window: QuietWindow) -> datetime:
        start = window.start_minutes()
        end = window.end_minutes()
        minute = value.hour * 60 + value.minute
        base = value.replace(hour=0, minute=0, second=0, microsecond=0)
        if start < end:
            return base + timedelta(minutes=end)
        if minute >= start:
            return base + timedelta(days=1, minutes=end)
        return base + timedelta(minutes=end)


def summarize_deliveries(
    items: list[tuple[str, datetime]],
    max_items: int,
    *,
    intro: str | None = None,
) -> str:
    """生成提醒摘要。"""
    visible = items[:max_items]
    lines = [
        intro or f"免打扰期间有 {len(items)} 条提醒被延后, 已为你合并成这一条摘要.",
        "需要关注的事项:",
    ]
    for title, due_at in visible:
        lines.append(f"- {title} (原计划 {due_at.strftime('%H:%M')})")
    if len(items) > max_items:
        lines.append(f"- 另外还有 {len(items) - max_items} 条")
    return "\n".join(lines)


__all__ = ["DeliveryPlan", "QuietPolicyEngine", "parse_clock_minutes", "summarize_deliveries"]
