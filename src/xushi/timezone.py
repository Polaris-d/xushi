"""时区工具。"""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo
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


def ensure_timezone_aware(value: datetime | None) -> datetime | None:
    """确保具体时间点携带时区信息。"""
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value
