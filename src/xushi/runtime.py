"""运行时调度循环。"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from xushi.models import Run
from xushi.service import XushiService

logger = logging.getLogger("xushi.scheduler")


def run_scheduler_once(service: XushiService, now: datetime | None = None) -> list[Run]:
    """执行一次到期任务和未完成跟进扫描。"""
    return service.tick(now or datetime.now(tz=UTC))


async def run_scheduler_loop(service: XushiService, interval_seconds: int) -> None:
    """后台循环扫描到期任务。"""
    logger.info("scheduler loop started interval_seconds=%s", interval_seconds)
    try:
        while True:
            try:
                runs = run_scheduler_once(service)
            except Exception:
                logger.exception("scheduler tick failed")
            else:
                if runs:
                    logger.info("scheduler tick created_runs=%s", len(runs))
                else:
                    logger.debug("scheduler tick completed created_runs=0")
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        logger.info("scheduler loop stopped")
        raise
