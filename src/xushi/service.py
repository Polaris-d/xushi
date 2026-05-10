"""序时应用服务。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from xushi.config import Settings
from xushi.executors import ExecutorRegistry
from xushi.models import (
    Executor,
    Run,
    RunCallback,
    RunStatus,
    Task,
    TaskCreate,
    TaskPatch,
    TaskStatus,
)
from xushi.notifications import NotificationDispatcher, NotificationEvent
from xushi.scheduler import Scheduler
from xushi.storage import SQLiteStore

ACTIVE_RUN_STATUSES = {RunStatus.PENDING_CONFIRMATION.value, RunStatus.FOLLOWING_UP.value}


class XushiService:
    """组合调度、执行器和持久化的应用服务。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = SQLiteStore(settings.database_path)
        self.scheduler = Scheduler()
        self.notifications = NotificationDispatcher()
        self.executors = ExecutorRegistry(self.notifications)
        self._executor_map = {
            executor.id: executor for executor in settings.executors if executor.enabled
        }

    def create_task(self, request: TaskCreate) -> Task:
        """创建任务。"""
        if request.idempotency_key:
            existing = self._find_task_by_idempotency_key(request.idempotency_key)
            if existing is not None:
                return existing
        task = request.to_task()
        return self.store.save_task(task)

    def list_tasks(self) -> list[Task]:
        """列出任务。"""
        return self.store.list_tasks()

    def get_task(self, task_id: str) -> Task | None:
        """获取任务。"""
        return self.store.get_task(task_id)

    def update_task(self, task_id: str, patch: TaskPatch) -> Task | None:
        """更新任务。"""
        task = self.get_task(task_id)
        if task is None:
            return None
        data = task.model_dump()
        patch_data = patch.model_dump(exclude_unset=True)
        data.update(patch_data)
        data["updated_at"] = datetime.now(tz=UTC)
        updated = Task.model_validate(data)
        return self.store.save_task(updated)

    def delete_task(self, task_id: str) -> bool:
        """归档任务，保留审计数据。"""
        task = self.get_task(task_id)
        if task is None:
            return False
        archived_at = datetime.now(tz=UTC)
        task.status = TaskStatus.ARCHIVED
        task.updated_at = archived_at
        self.store.save_task(task)
        self._cancel_open_runs_for_task(task_id, archived_at, "task_archived")
        return True

    def trigger_task(self, task_id: str, now: datetime | None = None) -> Run:
        """手动触发任务。"""
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        scheduled_for = now or datetime.now(tz=UTC)
        executor = None
        if task.action.executor_id:
            executor = self._get_executor(task.action.executor_id)
        task.action.payload.setdefault("title", task.title)
        task.action.payload.setdefault("task_id", task.id)
        result = self.executors.execute(task.action, executor)
        status = RunStatus.PENDING_CONFIRMATION
        if not task.follow_up_policy.requires_confirmation:
            status = RunStatus.SUCCEEDED if result.get("delivered") else RunStatus.FAILED
        run = Run(
            id=f"run_{uuid4().hex}",
            task_id=task.id,
            scheduled_for=scheduled_for,
            started_at=scheduled_for,
            finished_at=datetime.now(tz=UTC),
            status=status,
            result=result,
            error=result.get("error"),
        )
        notification_id = result.get("notification_id")
        if notification_id:
            self._save_notification_from_result(result, run.id, task.id, "reminder")
        return self.store.save_run(run)

    def confirm_run(self, run_id: str, now: datetime | None = None) -> Run | None:
        """确认运行记录已完成。"""
        run = self.store.get_run(run_id)
        if run is None:
            return None
        confirmed_at = now or datetime.now(tz=UTC)
        run.status = RunStatus.SUCCEEDED
        run.confirmed_at = confirmed_at
        run.finished_at = confirmed_at
        self.store.save_run(run)

        if run.origin_run_id:
            origin = self.store.get_run(run.origin_run_id)
            if origin is not None:
                origin.status = RunStatus.SUCCEEDED
                origin.confirmed_at = confirmed_at
                origin.finished_at = confirmed_at
                origin.result = {**origin.result, "confirmed_by_follow_up": run.id}
                self.store.save_run(origin)
            self._cancel_follow_ups_for_origin(
                run.origin_run_id,
                confirmed_at,
                "confirmed_by_follow_up",
                exclude_run_id=run.id,
            )
        else:
            self._cancel_follow_ups_for_origin(
                run.id,
                confirmed_at,
                "confirmed_by_origin",
            )
        return run

    def confirm_latest_run(self, task_id: str, now: datetime | None = None) -> Run | None:
        """确认某任务最近一次待确认主运行记录。"""
        pending_runs = [
            run
            for run in self.store.list_runs()
            if run.task_id == task_id
            and run.origin_run_id is None
            and run.confirmed_at is None
            and run.status == RunStatus.PENDING_CONFIRMATION
        ]
        if not pending_runs:
            return None
        latest = max(pending_runs, key=lambda item: item.scheduled_for)
        return self.confirm_run(latest.id, now)

    def callback_run(self, run_id: str, callback: RunCallback) -> Run | None:
        """根据外部执行器回调更新运行记录。"""
        run = self.store.get_run(run_id)
        if run is None:
            return None
        finished_at = callback.finished_at or datetime.now(tz=UTC)
        run.status = RunStatus(callback.status)
        run.result = {**run.result, **callback.result}
        run.error = callback.error
        run.finished_at = finished_at
        if callback.status == RunStatus.SUCCEEDED:
            run.confirmed_at = finished_at
        self.store.save_run(run)

        if run.origin_run_id and callback.status == RunStatus.SUCCEEDED:
            origin = self.store.get_run(run.origin_run_id)
            if origin is not None:
                origin.status = RunStatus.SUCCEEDED
                origin.confirmed_at = finished_at
                origin.finished_at = finished_at
                origin.result = {**origin.result, "confirmed_by_follow_up": run.id}
                self.store.save_run(origin)
            self._cancel_follow_ups_for_origin(
                run.origin_run_id,
                finished_at,
                "confirmed_by_follow_up",
                exclude_run_id=run.id,
            )
        elif callback.status == RunStatus.SUCCEEDED:
            self._cancel_follow_ups_for_origin(
                run.id,
                finished_at,
                "confirmed_by_origin",
            )
        return run

    def tick(self, now: datetime | None = None) -> list[Run]:
        """扫描并触发到期任务。"""
        current = now or datetime.now(tz=UTC)
        created: list[Run] = []
        for task in self.list_tasks():
            if task.status != TaskStatus.ACTIVE:
                continue
            last_run = self._last_primary_run_for_task(task.id)
            last_scheduled_for = last_run.scheduled_for if last_run else None
            last_completed_at = last_run.confirmed_at if last_run else None
            for scheduled_for in self.scheduler.due_occurrences(
                task,
                current,
                last_scheduled_for,
                last_completed_at,
            ):
                created.append(self.trigger_task(task.id, now=scheduled_for))
        created.extend(self.process_follow_ups(current))
        return created

    def process_follow_ups(self, now: datetime | None = None) -> list[Run]:
        """扫描未确认运行记录并生成跟进提醒。"""
        current = now or datetime.now(tz=UTC)
        created: list[Run] = []
        runs = self.list_runs()
        by_origin = self._group_follow_ups_by_origin(runs)
        for run in runs:
            if (
                run.origin_run_id is not None
                or run.confirmed_at is not None
                or run.status != RunStatus.PENDING_CONFIRMATION
            ):
                continue
            task = self.get_task(run.task_id)
            if (
                task is None
                or task.status != TaskStatus.ACTIVE
                or not task.follow_up_policy.requires_confirmation
            ):
                continue
            attempts = len(by_origin.get(run.id, []))
            next_at = self.scheduler.next_follow_up_at(
                scheduled_for=run.scheduled_for,
                policy=task.follow_up_policy,
                follow_up_attempts=attempts,
                now=current,
                confirmed_at=run.confirmed_at,
            )
            if next_at is None:
                continue
            executor = None
            if task.action.executor_id:
                executor = self._get_executor(task.action.executor_id)
            task.action.payload["title"] = task.title
            task.action.payload["task_id"] = task.id
            task.action.payload["kind"] = "follow_up"
            task.action.payload["message"] = f"{task.title} 仍未确认完成, 请确认或调整排期。"
            result = self.executors.execute(task.action, executor)
            follow_up_run = Run(
                id=f"run_{uuid4().hex}",
                task_id=task.id,
                origin_run_id=run.id,
                scheduled_for=next_at,
                started_at=current,
                finished_at=current,
                status=RunStatus.FOLLOWING_UP,
                result={
                    **result,
                    "follow_up": True,
                    "ask_reschedule": task.follow_up_policy.ask_reschedule_on_timeout,
                },
                error=result.get("error"),
                follow_up_attempts=attempts + 1,
            )
            notification_id = result.get("notification_id")
            if notification_id:
                self._save_notification_from_result(result, follow_up_run.id, task.id, "follow_up")
            created.append(self.store.save_run(follow_up_run))
        return created

    def list_runs(
        self,
        *,
        task_id: str | None = None,
        status: RunStatus | str | None = None,
        active_only: bool = False,
        limit: int | None = None,
    ) -> list[Run]:
        """列出运行历史。"""
        all_runs = self.store.list_runs()
        runs = all_runs
        if task_id is not None:
            runs = [run for run in runs if run.task_id == task_id]
        if status is not None:
            run_status = RunStatus(status)
            runs = [run for run in runs if run.status == run_status]
        if active_only:
            runs_by_id = {run.id: run for run in all_runs}
            tasks_by_id = {task.id: task for task in self.list_tasks()}
            runs = [
                run
                for run in runs
                if self._is_active_run(run, runs_by_id=runs_by_id, tasks_by_id=tasks_by_id)
            ]
        if limit is not None:
            runs = runs[:limit]
        return runs

    def get_run(self, run_id: str) -> Run | None:
        """获取运行记录。"""
        return self.store.get_run(run_id)

    def list_executors(self) -> list[Executor]:
        """列出执行器。"""
        return list(self.settings.executors)

    def list_notifications(self) -> list[NotificationEvent]:
        """列出通知事件。"""
        return self.store.list_notifications()

    def _get_executor(self, executor_id: str) -> Executor | None:
        """按 ID 获取启用的 executor 配置。"""
        return self._executor_map.get(executor_id)

    def _group_follow_ups_by_origin(self, runs: list[Run]) -> dict[str, list[Run]]:
        grouped: dict[str, list[Run]] = {}
        for run in runs:
            if run.origin_run_id is None:
                continue
            grouped.setdefault(run.origin_run_id, []).append(run)
        return grouped

    def _is_active_run(
        self,
        run: Run,
        *,
        runs_by_id: dict[str, Run],
        tasks_by_id: dict[str, Task],
    ) -> bool:
        """判断运行记录是否仍需要 agent 处理。"""
        if run.status not in ACTIVE_RUN_STATUSES or run.confirmed_at is not None:
            return False
        task = tasks_by_id.get(run.task_id)
        if task is None or task.status != TaskStatus.ACTIVE:
            return False
        if run.origin_run_id is None:
            return True
        origin = runs_by_id.get(run.origin_run_id)
        return (
            origin is not None
            and origin.status in ACTIVE_RUN_STATUSES
            and origin.confirmed_at is None
        )

    def _cancel_follow_ups_for_origin(
        self,
        origin_run_id: str,
        cancelled_at: datetime,
        reason: str,
        *,
        exclude_run_id: str | None = None,
    ) -> None:
        """取消同一主运行记录下尚未完成的跟进记录。"""
        for follow_up in self._group_follow_ups_by_origin(self.store.list_runs()).get(
            origin_run_id,
            [],
        ):
            if follow_up.id == exclude_run_id or follow_up.status not in ACTIVE_RUN_STATUSES:
                continue
            follow_up.status = RunStatus.CANCELLED
            follow_up.finished_at = cancelled_at
            follow_up.result = {**follow_up.result, "cancelled_reason": reason}
            self.store.save_run(follow_up)

    def _cancel_open_runs_for_task(
        self,
        task_id: str,
        cancelled_at: datetime,
        reason: str,
    ) -> None:
        """取消任务下仍在等待确认或跟进的运行记录。"""
        for run in self.store.list_runs():
            if run.task_id != task_id or run.status not in ACTIVE_RUN_STATUSES:
                continue
            run.status = RunStatus.CANCELLED
            run.finished_at = cancelled_at
            run.result = {**run.result, "cancelled_reason": reason}
            self.store.save_run(run)

    def _last_primary_run_for_task(self, task_id: str) -> Run | None:
        primary_runs = [
            run for run in self.list_runs() if run.task_id == task_id and run.origin_run_id is None
        ]
        if not primary_runs:
            return None
        return max(primary_runs, key=lambda run: run.scheduled_for)

    def _find_task_by_idempotency_key(self, idempotency_key: str) -> Task | None:
        for task in self.list_tasks():
            if task.idempotency_key == idempotency_key:
                return task
        return None

    def _save_notification_from_result(
        self,
        result: dict[str, object],
        run_id: str,
        task_id: str,
        kind: str,
    ) -> None:
        event = NotificationEvent(
            id=str(result["notification_id"]),
            run_id=run_id,
            task_id=task_id,
            kind=kind,
            channel=str(result.get("notification_channel", "system")),
            title=str(result.get("payload", {}).get("title", "序时提醒"))
            if isinstance(result.get("payload"), dict)
            else "序时提醒",
            message=str(result.get("payload", {}).get("message", ""))
            if isinstance(result.get("payload"), dict)
            else "",
            status=str(result.get("notification_status", "fallback_logged")),
        )
        self.store.save_notification(event)
