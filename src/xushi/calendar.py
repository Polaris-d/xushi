"""工作日日历与节假日判断。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from importlib import resources
from typing import Any


def _load_2026_calendar_data() -> tuple[dict[date, str], dict[date, str]]:
    data_file = resources.files("xushi.data").joinpath("china_holidays_2026.json")
    payload = json.loads(data_file.read_text(encoding="utf-8"))
    holidays = _named_dates(payload["holidays"])
    adjusted_workdays = _named_dates(payload["adjusted_workdays"])
    return holidays, adjusted_workdays


def _named_dates(groups: list[dict[str, Any]]) -> dict[date, str]:
    named_dates: dict[date, str] = {}
    for group in groups:
        name = str(group["name"])
        for value in group["dates"]:
            named_dates[date.fromisoformat(value)] = name
    return named_dates


def _default_holidays() -> dict[date, str]:
    return _load_2026_calendar_data()[0]


def _default_adjusted_workdays() -> dict[date, str]:
    return _load_2026_calendar_data()[1]


@dataclass(frozen=True)
class ChinaWorkdayCalendar:
    """中国大陆工作日日历。

    当前内置 2026 年春节调休样例，后续可接入可更新的年度数据文件。
    """

    holidays: dict[date, str] = field(default_factory=_default_holidays)
    adjusted_workdays: dict[date, str] = field(default_factory=_default_adjusted_workdays)

    def is_workday(self, value: date) -> bool:
        """判断日期是否为工作日。"""
        if value in self.adjusted_workdays:
            return True
        if value in self.holidays:
            return False
        return value.weekday() < 5

    def holiday_name(self, value: date) -> str | None:
        """返回法定节假日名称。"""
        return self.holidays.get(value)

    def adjusted_workday_name(self, value: date) -> str | None:
        """返回调休工作日关联的节日名称。"""
        return self.adjusted_workdays.get(value)

    def next_workday(self, value: date) -> date:
        """返回从给定日期开始的下一个工作日。"""
        current = value
        while not self.is_workday(current):
            current += timedelta(days=1)
        return current
