"""运行记录状态流转服务。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from xushi.models import Run, RunCallback, RunStatus
from xushi.storage import SQLiteStore


class RunLifecycleService:
    """集中处理 run 成功确认后的级联状态更新。"""

    def __init__(
        self,
        store: SQLiteStore,
        cancel_deliveries_for_run: Callable[[str, datetime, str], None],
        cancel_follow_ups_for_origin: Callable[..., None],
    ) -> None:
        self.store = store
        self._cancel_deliveries_for_run = cancel_deliveries_for_run
        self._cancel_follow_ups_for_origin = cancel_follow_ups_for_origin

    def confirm_success(
        self,
        run: Run,
        confirmed_at: datetime,
        *,
        delivery_reason: str,
        result_update: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> Run:
        """将 run 标记为成功，并同步 origin/follow-up 级联关系。"""
        if result_update:
            run.result = {**run.result, **result_update}
        run.status = RunStatus.SUCCEEDED
        run.confirmed_at = confirmed_at
        run.finished_at = confirmed_at
        run.error = error
        self.store.save_run(run)
        self._cancel_deliveries_for_run(run.id, confirmed_at, delivery_reason)
        self._propagate_success(run, confirmed_at)
        return run

    def apply_callback(self, run: Run, callback: RunCallback) -> Run:
        """根据 executor callback 更新 run。"""
        finished_at = callback.finished_at or datetime.now(tz=UTC)
        callback_status = RunStatus(callback.status)
        if callback_status == RunStatus.SUCCEEDED:
            return self.confirm_success(
                run,
                finished_at,
                delivery_reason="callback_succeeded",
                result_update=callback.result,
                error=callback.error,
            )

        run.status = callback_status
        run.result = {**run.result, **callback.result}
        run.error = callback.error
        run.finished_at = finished_at
        self.store.save_run(run)
        return run

    def _propagate_success(self, run: Run, confirmed_at: datetime) -> None:
        """成功确认后取消 sibling follow-up 或同步 origin。"""
        if run.origin_run_id:
            origin = self.store.get_run(run.origin_run_id)
            if origin is not None:
                origin.status = RunStatus.SUCCEEDED
                origin.confirmed_at = confirmed_at
                origin.finished_at = confirmed_at
                origin.result = {**origin.result, "confirmed_by_follow_up": run.id}
                self.store.save_run(origin)
                self._cancel_deliveries_for_run(
                    origin.id,
                    confirmed_at,
                    "confirmed_by_follow_up",
                )
            self._cancel_follow_ups_for_origin(
                run.origin_run_id,
                confirmed_at,
                "confirmed_by_follow_up",
                exclude_run_id=run.id,
            )
            return

        self._cancel_follow_ups_for_origin(
            run.id,
            confirmed_at,
            "confirmed_by_origin",
        )
