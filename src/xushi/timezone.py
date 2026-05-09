"""时区工具。"""

from __future__ import annotations

from datetime import UTC, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil import tz


def get_tzinfo(name: str) -> tzinfo:
    """返回时区对象。

    Windows 最小 Python 环境可能没有 IANA tzdata，因此 UTC 做内置兜底，
    其他时区优先使用标准库，失败后尝试 dateutil。
    """
    if name in {"UTC", "Etc/UTC", "Z"}:
        return UTC
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        fallback = tz.gettz(name)
        if fallback is None:
            raise
        return fallback
