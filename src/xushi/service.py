"""序时应用服务。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from xushi.bridges import DEFAULT_OPENCLAW_HOOKS_AGENT_URL
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


class XushiService:
    """组合调度、执行器和持久化的应用服务。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = SQLiteStore(settings.database_path)
        self.scheduler = Scheduler()
        self.notifications = NotificationDispatcher()
        self.executors = ExecutorRegistry(self.notifications)
        self._ensure_builtin_executors()

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
        task.status = TaskStatus.ARCHIVED
        task.updated_at = datetime.now(tz=UTC)
        self.store.save_task(task)
        return True

    def trigger_task(self, task_id: str, now: datetime | None = None) -> Run:
        """手动触发任务。"""
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        scheduled_for = now or datetime.now(tz=UTC)
        executor = None
        if task.action.executor_id:
            executor = self.store.get_executor(task.action.executor_id)
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
                self.store.save_run(origin)
        return run

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
            if run.origin_run_id is not None or run.confirmed_at is not None:
                continue
            task = self.get_task(run.task_id)
            if task is None or not task.follow_up_policy.requires_confirmation:
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
                executor = self.store.get_executor(task.action.executor_id)
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

    def list_runs(self) -> list[Run]:
        """列出运行历史。"""
        return self.store.list_runs()

    def get_run(self, run_id: str) -> Run | None:
        """获取运行记录。"""
        return self.store.get_run(run_id)

    def list_executors(self) -> list[Executor]:
        """列出执行器。"""
        return self.store.list_executors()

    def save_executor(self, executor: Executor) -> Executor:
        """保存执行器。"""
        return self.store.save_executor(executor)

    def list_notifications(self) -> list[NotificationEvent]:
        """列出通知事件。"""
        return self.store.list_notifications()

    def _ensure_builtin_executors(self) -> None:
        for executor in (
            Executor(
                id="openclaw",
                kind="openclaw",
                name="OpenClaw",
                config={
                    "mode": "hooks_agent",
                    "webhook_url": DEFAULT_OPENCLAW_HOOKS_AGENT_URL,
                    "token_env": "OPENCLAW_HOOKS_TOKEN",
                    "channel": "last",
                    "deliver": True,
                    "timeout_seconds": 120,
                },
            ),
            Executor(id="hermes", kind="hermes", name="Hermes", config={"mode": "template"}),
        ):
            if self.store.get_executor(executor.id) is None:
                self.store.save_executor(executor)

    def _group_follow_ups_by_origin(self, runs: list[Run]) -> dict[str, list[Run]]:
        grouped: dict[str, list[Run]] = {}
        for run in runs:
            if run.origin_run_id is None:
                continue
            grouped.setdefault(run.origin_run_id, []).append(run)
        return grouped

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
