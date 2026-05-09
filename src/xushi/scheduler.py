"""任务时间计算与跟进策略。"""

from __future__ import annotations

from datetime import datetime, timedelta

from dateutil.rrule import rrulestr

from xushi.calendar import ChinaWorkdayCalendar
from xushi.models import FollowUpPolicy, MissedPolicy, Task


def parse_iso_duration(value: str | None) -> timedelta:
    """解析常用 ISO 8601 duration。

    v1 先支持 `PT30S`、`PT5M`、`PT1H` 以及它们的组合。
    """
    if not value:
        return timedelta(0)
    if not value.startswith("PT"):
        raise ValueError(f"unsupported duration: {value}")
    seconds = 0
    number = ""
    for char in value[2:]:
        if char.isdigit():
            number += char
            continue
        if not number:
            raise ValueError(f"invalid duration: {value}")
        amount = int(number)
        number = ""
        if char == "H":
            seconds += amount * 3600
        elif char == "M":
            seconds += amount * 60
        elif char == "S":
            seconds += amount
        else:
            raise ValueError(f"unsupported duration unit: {char}")
    if number:
        raise ValueError(f"invalid duration: {value}")
    return timedelta(seconds=seconds)


class Scheduler:
    """计算任务触发时间与未完成跟进时间。"""

    def __init__(self, calendar: ChinaWorkdayCalendar | None = None) -> None:
        self.calendar = calendar or ChinaWorkdayCalendar()

    def due_occurrences(
        self,
        task: Task,
        now: datetime,
        last_scheduled_for: datetime | None,
        last_completed_at: datetime | None = None,
    ) -> list[datetime]:
        """返回当前应触发的调度时间列表。"""
        schedule = task.schedule
        if schedule.kind == "one_shot":
            if schedule.run_at is None:
                return []
            scheduled_for = self._apply_calendar_policy(schedule.run_at, schedule.calendar_policy)
            if last_scheduled_for is not None or scheduled_for > now:
                return []
            if self._is_expired(scheduled_for, schedule.expiry, now):
                return []
            return [scheduled_for]

        if schedule.kind == "window":
            if schedule.window_start is None or schedule.window_end is None:
                return []
            window_start = self._apply_calendar_policy(
                schedule.window_start,
                schedule.calendar_policy,
            )
            window_end = schedule.window_end + (window_start - schedule.window_start)
            if last_scheduled_for is not None or now < window_start or now > window_end:
                return []
            if self._is_expired(window_start, schedule.expiry, now):
                return []
            return [window_start]

        if schedule.kind == "deadline":
            if schedule.deadline is None:
                return []
            deadline = self._apply_calendar_policy(schedule.deadline, schedule.calendar_policy)
            if last_scheduled_for is not None or deadline > now:
                return []
            if self._is_expired(deadline, schedule.expiry, now):
                return []
            return [deadline]

        if schedule.kind == "floating":
            return []

        if schedule.kind == "asap":
            scheduled_for = self._apply_calendar_policy(task.created_at, schedule.calendar_policy)
            if last_scheduled_for is not None or scheduled_for > now:
                return []
            if self._is_expired(scheduled_for, schedule.expiry, now):
                return []
            return [scheduled_for]

        if schedule.kind != "recurring" or schedule.run_at is None or not schedule.rrule:
            return []

        dtstart = schedule.run_at
        start_after = last_scheduled_for or schedule.run_at
        include_start = last_scheduled_for is None
        if schedule.anchor == "completion" and last_scheduled_for is not None:
            if last_completed_at is None:
                return []
            dtstart = last_completed_at
            start_after = last_completed_at
            include_start = False

        rule = rrulestr(schedule.rrule, dtstart=dtstart)
        raw_occurrences = list(rule.between(start_after, now, inc=include_start))
        occurrences = self._eligible_occurrences(raw_occurrences, task, now)
        if not occurrences:
            return []

        if schedule.missed_policy == MissedPolicy.SKIP:
            return []
        if schedule.missed_policy == MissedPolicy.CATCH_UP_ALL:
            return occurrences
        if schedule.missed_policy == MissedPolicy.FAIL:
            return []
        return [occurrences[-1]]

    def next_follow_up_at(
        self,
        scheduled_for: datetime,
        policy: FollowUpPolicy,
        follow_up_attempts: int,
        now: datetime,
        confirmed_at: datetime | None,
    ) -> datetime | None:
        """计算下一次跟进提醒时间。"""
        if confirmed_at is not None or not policy.requires_confirmation:
            return None
        if policy.max_attempts <= 0 or follow_up_attempts >= policy.max_attempts:
            return None

        due_at = scheduled_for + parse_iso_duration(policy.grace_period)
        due_at += parse_iso_duration(policy.interval) * follow_up_attempts
        if now >= due_at:
            return due_at
        return None

    def _is_expired(self, scheduled_for: datetime, expiry: str | None, now: datetime) -> bool:
        if not expiry:
            return False
        return now > scheduled_for + parse_iso_duration(expiry)

    def _eligible_occurrences(
        self,
        occurrences: list[datetime],
        task: Task,
        now: datetime,
    ) -> list[datetime]:
        schedule = task.schedule
        eligible: list[datetime] = []
        seen: set[datetime] = set()
        for occurrence in occurrences:
            scheduled_for = self._apply_calendar_policy(occurrence, schedule.calendar_policy)
            if scheduled_for in seen or scheduled_for > now:
                continue
            if self._is_expired(scheduled_for, schedule.expiry, now):
                continue
            seen.add(scheduled_for)
            eligible.append(scheduled_for)
        return eligible

    def _apply_calendar_policy(self, value: datetime, calendar_policy: str) -> datetime:
        if calendar_policy != "workday":
            return value
        next_workday = self.calendar.next_workday(value.date())
        if next_workday == value.date():
            return value
        return value + (next_workday - value.date())
