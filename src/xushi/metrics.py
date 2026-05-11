"""运行期内存指标。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


def _default_counters() -> dict[str, int | float]:
    """返回稳定的指标键，方便 agent 和监控端解析。"""
    return {
        "runs_created_total": 0,
        "deliveries_succeeded_total": 0,
        "deliveries_failed_total": 0,
        "deliveries_delayed_total": 0,
        "follow_up_created_total": 0,
        "auto_retry_created_total": 0,
        "tick_count_total": 0,
        "tick_duration_ms": 0.0,
    }


@dataclass
class RuntimeMetrics:
    """保存 daemon 当前进程内的轻量运行指标。"""

    counters: dict[str, int | float] = field(default_factory=_default_counters)
    recent_ticks: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=20))

    def increment(self, key: str, amount: int = 1) -> None:
        """累加一个计数器。"""
        self.counters[key] = self.counters.get(key, 0) + amount

    def record_delivery_status(self, status: str) -> None:
        """按投递最终状态累加指标。"""
        if status == "delivered":
            self.increment("deliveries_succeeded_total")
        elif status == "failed":
            self.increment("deliveries_failed_total")
        elif status == "delayed":
            self.increment("deliveries_delayed_total")

    def record_tick(
        self,
        *,
        at: str,
        duration_ms: float,
        processed_deliveries: int,
        created_runs: int,
        created_follow_ups: int,
        auto_retries: int,
    ) -> None:
        """记录一次 scheduler tick 摘要。"""
        rounded_duration = round(duration_ms, 3)
        self.increment("tick_count_total")
        self.counters["tick_duration_ms"] = rounded_duration
        self.recent_ticks.append(
            {
                "at": at,
                "duration_ms": rounded_duration,
                "processed_deliveries": processed_deliveries,
                "created_runs": created_runs,
                "created_follow_ups": created_follow_ups,
                "auto_retries": auto_retries,
            }
        )

    def snapshot(self) -> dict[str, Any]:
        """返回可 JSON 序列化的指标快照。"""
        return {
            "counters": dict(self.counters),
            "recent_ticks": list(self.recent_ticks),
        }
