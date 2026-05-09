"""运行时调度循环。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from xushi.models import Run
from xushi.service import XushiService


def run_scheduler_once(service: XushiService, now: datetime | None = None) -> list[Run]:
    """执行一次到期任务和未完成跟进扫描。"""
    return service.tick(now or datetime.now(tz=UTC))


async def run_scheduler_loop(service: XushiService, interval_seconds: int) -> None:
    """后台循环扫描到期任务。"""
    while True:
        run_scheduler_once(service)
        await asyncio.sleep(interval_seconds)
