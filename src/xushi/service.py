"""序时应用服务。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from xushi.config import Settings
from xushi.delivery import QuietPolicyEngine, summarize_deliveries
from xushi.executors import ExecutorRegistry
from xushi.lifecycle import RunLifecycleService
from xushi.metrics import RuntimeMetrics
from xushi.models import (
    Action,
    Delivery,
    DeliveryStatus,
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
from xushi.storage import SQLiteStore, dump_json

ACTIVE_RUN_STATUSES = {
    RunStatus.PENDING_DELIVERY.value,
    RunStatus.PENDING_CONFIRMATION.value,
    RunStatus.FOLLOWING_UP.value,
}
COMPLETABLE_PRIMARY_RUN_STATUSES = {
    RunStatus.PENDING_DELIVERY.value,
    RunStatus.PENDING_CONFIRMATION.value,
    RunStatus.FAILED.value,
}
DELIVERABLE_STATUSES = {DeliveryStatus.PENDING.value, DeliveryStatus.DELAYED.value}


class IdempotencyConflictError(ValueError):
    """同一幂等键被用于不同请求。"""


class InvalidTaskConfigurationError(ValueError):
    """任务配置无法形成有效调度语义。"""


class XushiService:
    """组合调度、执行器和持久化的应用服务。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = SQLiteStore(
            settings.database_path,
            journal_mode=settings.sqlite_journal_mode,
            synchronous=settings.sqlite_synchronous,
        )
        self.scheduler = Scheduler()
        self.quiet_policy = QuietPolicyEngine(settings.quiet_policy, self.scheduler.calendar)
        self.notifications = NotificationDispatcher()
        self.executors = ExecutorRegistry(self.notifications)
        self.metrics = RuntimeMetrics()
        self.lifecycle = RunLifecycleService(
            self.store,
            self._cancel_deliveries_for_run,
            self._cancel_follow_ups_for_origin,
        )
        self._executor_map = {
            executor.id: executor for executor in settings.executors if executor.enabled
        }

    def create_task(self, request: TaskCreate) -> Task:
        """创建任务。"""
        idempotency_hash = (
            self._idempotency_hash(request) if request.idempotency_key else None
        )
        if request.idempotency_key:
            existing = self.store.get_task_by_idempotency_key(request.idempotency_key)
            if existing is not None:
                existing_hash = self.store.get_task_idempotency_hash(request.idempotency_key)
                if existing_hash is not None and existing_hash != idempotency_hash:
                    raise IdempotencyConflictError("idempotency key conflict")
                return existing
        task = request.to_task()
        self._validate_task_contract(task)
        return self.store.save_task(task, idempotency_hash=idempotency_hash)

    def list_tasks(self, *, limit: int | None = None) -> list[Task]:
        """列出任务。"""
        return self.store.list_tasks(limit=limit)

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
        self._validate_task_contract(updated)
        self._validate_task_schedule_transition(task, updated)
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
        run = Run(
            id=f"run_{uuid4().hex}",
            task_id=task.id,
            scheduled_for=scheduled_for,
            started_at=scheduled_for,
            status=RunStatus.PENDING_DELIVERY,
        )
        self.store.save_run(run)
        self.metrics.increment("runs_created_total")
        action = self._action_for_run(task, run, kind="reminder")
        delivery = self._create_delivery(task, run, action, kind="reminder", due_at=scheduled_for)
        if delivery.status in {DeliveryStatus.SKIPPED, DeliveryStatus.SILENCED}:
            return self._complete_prevented_delivery(run, task, delivery, scheduled_for)
        self.process_deliveries(scheduled_for)
        return self.get_run(run.id) or run

    def confirm_run(self, run_id: str, now: datetime | None = None) -> Run | None:
        """确认运行记录已完成。"""
        run = self.store.get_run(run_id)
        if run is None:
            return None
        confirmed_at = now or datetime.now(tz=UTC)
        return self.lifecycle.confirm_success(
            run,
            confirmed_at,
            delivery_reason="confirmed",
        )

    def confirm_latest_run(self, task_id: str, now: datetime | None = None) -> Run | None:
        """确认某任务最近一次待确认主运行记录。"""
        latest = self.store.latest_pending_primary_run_for_task(task_id)
        if latest is None:
            return None
        return self.confirm_run(latest.id, now)

    def complete_task(self, task_id: str, now: datetime | None = None) -> Run | None:
        """按任务记录完成，必要时为完成锚点创建手动 run。"""
        task = self.get_task(task_id)
        if task is None:
            return None
        if task.status != TaskStatus.ACTIVE:
            return None
        completed_at = now or datetime.now(tz=UTC)
        latest = self.store.latest_unconfirmed_primary_run_for_task(
            task_id,
            COMPLETABLE_PRIMARY_RUN_STATUSES,
        )
        if latest is not None:
            return self.lifecycle.confirm_success(
                latest,
                completed_at,
                delivery_reason="task_completed",
                result_update={"completion_source": "task_complete"},
            )
        if not self._uses_completion_anchor(task):
            return None

        run = Run(
            id=f"run_{uuid4().hex}",
            task_id=task.id,
            scheduled_for=completed_at,
            started_at=completed_at,
            finished_at=completed_at,
            status=RunStatus.SUCCEEDED,
            confirmed_at=completed_at,
            result={
                "manual_completion": True,
                "completion_source": "task_complete",
            },
        )
        self.store.save_run(run)
        self.metrics.increment("runs_created_total")
        return run

    def callback_run(self, run_id: str, callback: RunCallback) -> Run | None:
        """根据外部执行器回调更新运行记录。"""
        run = self.store.get_run(run_id)
        if run is None:
            return None
        return self.lifecycle.apply_callback(run, callback)

    def tick(self, now: datetime | None = None) -> list[Run]:
        """扫描并触发到期任务。"""
        current = now or datetime.now(tz=UTC)
        started = perf_counter()
        processed_deliveries = self.process_deliveries(current)
        created: list[Run] = []
        for task in self.store.list_active_tasks():
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
        follow_ups = self.process_follow_ups(current)
        created.extend(follow_ups)
        auto_retries = self._auto_retry_failed_deliveries(current)
        self.metrics.record_tick(
            at=current.isoformat(),
            duration_ms=(perf_counter() - started) * 1000,
            processed_deliveries=len(processed_deliveries),
            created_runs=len(created),
            created_follow_ups=len(follow_ups),
            auto_retries=len(auto_retries),
        )
        return created

    def process_deliveries(self, now: datetime | None = None) -> list[Delivery]:
        """投递到期的提醒或免打扰摘要。"""
        current = now or datetime.now(tz=UTC)
        due_deliveries = self.store.list_due_deliveries(
            current,
            statuses=DELIVERABLE_STATUSES,
        )
        deliverable: list[Delivery] = []
        grouped_delivery_ids: set[str] = set()
        processed: list[Delivery] = []

        for delivery in due_deliveries:
            if self._delivery_is_still_needed(delivery):
                deliverable.append(delivery)
                continue
            processed.append(
                self._cancel_delivery(
                    delivery,
                    current,
                    "run_no_longer_waiting_delivery",
                )
            )

        groups: dict[tuple[str, str], list[Delivery]] = {}
        for delivery in deliverable:
            task = self.get_task(delivery.task_id) if delivery.task_id else None
            if (
                delivery.status == DeliveryStatus.DELAYED
                and task is not None
                and self.quiet_policy.should_aggregate(task)
            ):
                key = (delivery.action.type, delivery.action.executor_id or "system")
                groups.setdefault(key, []).append(delivery)

        for group in groups.values():
            if len(group) < 2:
                continue
            digest = self._execute_digest(group, current)
            processed.append(digest)
            grouped_delivery_ids.update(delivery.id for delivery in group)

        for delivery in deliverable:
            if delivery.id in grouped_delivery_ids:
                continue
            processed.append(self._execute_delivery(delivery, current))
        return processed

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
            follow_up_run = Run(
                id=f"run_{uuid4().hex}",
                task_id=task.id,
                origin_run_id=run.id,
                scheduled_for=next_at,
                started_at=current,
                status=RunStatus.PENDING_DELIVERY,
                result={"follow_up": True},
                follow_up_attempts=attempts + 1,
            )
            self.store.save_run(follow_up_run)
            self.metrics.increment("runs_created_total")
            self.metrics.increment("follow_up_created_total")
            action = self._action_for_run(task, follow_up_run, kind="follow_up")
            delivery = self._create_delivery(
                task,
                follow_up_run,
                action,
                kind="follow_up",
                due_at=next_at,
            )
            if delivery.status in {DeliveryStatus.SKIPPED, DeliveryStatus.SILENCED}:
                created.append(
                    self._complete_prevented_delivery(follow_up_run, task, delivery, current)
                )
                continue
            self.process_deliveries(current)
            created.append(self.get_run(follow_up_run.id) or follow_up_run)
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
        if active_only:
            all_runs = self.store.list_runs(task_id=task_id) if task_id else self.store.list_runs()
            runs = all_runs
            if status is not None:
                run_status = RunStatus(status)
                runs = [run for run in runs if run.status == run_status]
            runs_by_id = {run.id: run for run in all_runs}
            tasks_by_id = {task.id: task for task in self.list_tasks()}
            runs = [
                run
                for run in runs
                if self._is_active_run(run, runs_by_id=runs_by_id, tasks_by_id=tasks_by_id)
            ]
        else:
            runs = self.store.list_runs(task_id=task_id, status=status, limit=limit)
            return runs
        if limit is not None:
            runs = runs[:limit]
        return runs

    def get_run(self, run_id: str) -> Run | None:
        """获取运行记录。"""
        return self.store.get_run(run_id)

    def list_executors(self) -> list[Executor]:
        """列出执行器。"""
        return list(self.settings.executors)

    def reload_runtime_settings(self, settings: Settings) -> dict[str, object]:
        """热更新可运行时替换的配置。"""
        self.settings = replace(
            self.settings,
            quiet_policy=settings.quiet_policy,
            executors=settings.executors,
            auto_retry_failed_deliveries=settings.auto_retry_failed_deliveries,
            auto_retry_max_attempts=settings.auto_retry_max_attempts,
        )
        self.quiet_policy = QuietPolicyEngine(
            settings.quiet_policy,
            self.scheduler.calendar,
        )
        self._executor_map = {
            executor.id: executor for executor in settings.executors if executor.enabled
        }
        return {
            "reloaded": ["executors", "quiet_policy", "auto_retry_policy"],
            "restart_required": [
                "api_token",
                "database_path",
                "host",
                "port",
                "scheduler_interval_seconds",
                "sqlite_journal_mode",
                "sqlite_synchronous",
            ],
            "executors": len(settings.executors),
            "enabled_executors": len(self._executor_map),
            "quiet_policy_enabled": settings.quiet_policy.enabled,
            "auto_retry_failed_deliveries": settings.auto_retry_failed_deliveries,
            "auto_retry_max_attempts": settings.auto_retry_max_attempts,
        }

    def list_notifications(self) -> list[NotificationEvent]:
        """列出通知事件。"""
        return self.store.list_notifications()

    def list_deliveries(self, *, limit: int | None = None) -> list[Delivery]:
        """列出投递计划。"""
        return self.store.list_deliveries(limit=limit)

    def retry_failed_deliveries(
        self,
        now: datetime | None = None,
        *,
        limit: int | None = None,
        automatic: bool = False,
        max_attempts: int | None = None,
    ) -> list[Delivery]:
        """为仍需投递的失败 delivery 创建一次新的投递尝试。"""
        current = now or datetime.now(tz=UTC)
        created: list[Delivery] = []
        for delivery in self.store.list_deliveries(statuses={DeliveryStatus.FAILED.value}):
            if limit is not None and len(created) >= limit:
                break
            if not self._failed_delivery_can_retry(
                delivery,
                automatic=automatic,
                max_attempts=max_attempts,
            ):
                continue
            created.append(
                self._create_retry_delivery(
                    delivery,
                    current,
                    automatic=automatic,
                )
            )

        if created:
            self.process_deliveries(current)
        return [self.store.get_delivery(delivery.id) or delivery for delivery in created]

    def metrics_snapshot(self) -> dict[str, object]:
        """返回当前进程内的运行指标。"""
        return self.metrics.snapshot()

    def _get_executor(self, executor_id: str) -> Executor | None:
        """按 ID 获取启用的 executor 配置。"""
        return self._executor_map.get(executor_id)

    def _delivery_is_still_needed(self, delivery: Delivery) -> bool:
        """判断投递计划是否仍然对应一个等待投递的运行记录。"""
        if delivery.run_id is None:
            return True
        run = self.get_run(delivery.run_id)
        return run is not None and run.status == RunStatus.PENDING_DELIVERY

    def _cancel_delivery(
        self,
        delivery: Delivery,
        cancelled_at: datetime,
        reason: str,
    ) -> Delivery:
        """取消一条尚未执行的投递计划。"""
        delivery.status = DeliveryStatus.CANCELLED
        delivery.updated_at = cancelled_at
        delivery.result = {**delivery.result, "cancelled_reason": reason}
        self.store.save_delivery(delivery)
        return delivery

    def _cancel_deliveries_for_run(
        self,
        run_id: str,
        cancelled_at: datetime,
        reason: str,
    ) -> None:
        """取消某运行记录下尚未执行的投递计划。"""
        for delivery in self.store.list_deliveries_for_run(
            run_id,
            statuses=DELIVERABLE_STATUSES,
        ):
            self._cancel_delivery(delivery, cancelled_at, reason)

    def _action_for_run(self, task: Task, run: Run, *, kind: str) -> Action:
        """生成投递时使用的动作快照。"""
        payload = dict(task.action.payload)
        payload["title"] = task.title
        payload["task_id"] = task.id
        payload["run_id"] = run.id
        payload["kind"] = kind
        if kind == "follow_up":
            payload["message"] = f"{task.title} 仍未确认完成, 请确认或调整排期。"
        return Action(type=task.action.type, executor_id=task.action.executor_id, payload=payload)

    def _create_delivery(
        self,
        task: Task,
        run: Run,
        action: Action,
        *,
        kind: str,
        due_at: datetime,
    ) -> Delivery:
        """为一次到期事实创建投递计划。"""
        plan = self.quiet_policy.plan(task, due_at)
        now = datetime.now(tz=UTC)
        delivery = Delivery(
            id=f"delivery_{uuid4().hex}",
            run_id=run.id,
            task_id=task.id,
            kind=kind,
            action=action,
            due_at=due_at,
            deliver_at=plan.deliver_at,
            status=DeliveryStatus(plan.status),
            reason=plan.reason,
            created_at=now,
            updated_at=now,
        )
        run.result = {
            **run.result,
            "delivery_id": delivery.id,
            "delivery_status": delivery.status,
            "deliver_at": delivery.deliver_at.isoformat(),
        }
        self.store.save_run(run)
        self.metrics.record_delivery_status(str(delivery.status))
        return self.store.save_delivery(delivery)

    def _complete_prevented_delivery(
        self,
        run: Run,
        task: Task,
        delivery: Delivery,
        finished_at: datetime,
    ) -> Run:
        """处理 skip/silent 等不会主动投递的计划。"""
        delivery.updated_at = finished_at
        delivery.result = {"prevented_by": delivery.reason or "quiet_policy"}
        self.store.save_delivery(delivery)

        if delivery.status == DeliveryStatus.SKIPPED:
            run.status = RunStatus.CANCELLED
            run.error = "delivery skipped by quiet policy"
        elif task.follow_up_policy.requires_confirmation and delivery.kind == "reminder":
            run.status = RunStatus.PENDING_CONFIRMATION
        else:
            run.status = RunStatus.SUCCEEDED
        run.finished_at = finished_at
        run.result = {
            **run.result,
            "delivery_status": delivery.status,
            "quiet_policy_reason": delivery.reason,
        }
        return self.store.save_run(run)

    def _execute_delivery(self, delivery: Delivery, current: datetime) -> Delivery:
        """执行单条投递计划并更新对应运行记录。"""
        executor = (
            self._get_executor(delivery.action.executor_id)
            if delivery.action.executor_id
            else None
        )
        result = self.executors.execute(delivery.action, executor)
        delivered = bool(result.get("delivered"))
        delivery.status = DeliveryStatus.DELIVERED if delivered else DeliveryStatus.FAILED
        delivery.result = {**delivery.result, **result}
        delivery.error = result.get("error")
        delivery.updated_at = current
        self.store.save_delivery(delivery)
        self.metrics.record_delivery_status(str(delivery.status))

        notification_id = result.get("notification_id")
        if notification_id:
            self._save_notification_from_result(
                result,
                delivery.run_id,
                delivery.task_id,
                delivery.kind,
            )
        self._update_run_after_delivery(delivery, result, current)
        return delivery

    def _execute_digest(self, deliveries: list[Delivery], current: datetime) -> Delivery:
        """将多条延迟提醒合并成一条摘要投递。"""
        first = deliveries[0]
        items: list[tuple[str, datetime]] = []
        run_ids: list[str] = []
        for delivery in deliveries:
            title = str(delivery.action.payload.get("title") or "序时提醒")
            items.append((title, delivery.due_at))
            if delivery.run_id:
                run_ids.append(delivery.run_id)

        task = self.get_task(first.task_id) if first.task_id else None
        max_items = 10
        if task is not None:
            max_items = self.quiet_policy.effective_policy(task).aggregation.max_items
        action = Action(
            type=first.action.type,
            executor_id=first.action.executor_id,
            payload={
                "title": "序时免打扰摘要",
                "message": summarize_deliveries(items, max_items),
                "kind": "digest",
                "run_ids": run_ids,
            },
        )
        digest = Delivery(
            id=f"delivery_{uuid4().hex}",
            kind="digest",
            action=action,
            due_at=min(delivery.due_at for delivery in deliveries),
            deliver_at=current,
            status=DeliveryStatus.PENDING,
            digest_run_ids=run_ids,
            created_at=current,
            updated_at=current,
        )
        self.store.save_delivery(digest)
        executed = self._execute_delivery(digest, current)
        delivered = executed.status == DeliveryStatus.DELIVERED

        for delivery in deliveries:
            delivery.status = DeliveryStatus.DIGESTED if delivered else DeliveryStatus.FAILED
            delivery.grouped_delivery_id = digest.id
            delivery.result = {
                "digest_delivery_id": digest.id,
                "digest_status": executed.status,
            }
            delivery.error = executed.error
            delivery.updated_at = current
            self.store.save_delivery(delivery)
            self.metrics.record_delivery_status(str(delivery.status))
            result = {
                **executed.result,
                "delivered": delivered,
                "digest_delivery_id": digest.id,
            }
            self._update_run_after_delivery(delivery, result, current)
        return executed

    def _update_run_after_delivery(
        self,
        delivery: Delivery,
        result: dict[str, object],
        delivered_at: datetime,
    ) -> None:
        """根据投递结果更新 run 状态。"""
        if delivery.run_id is None or delivery.task_id is None:
            return
        run = self.get_run(delivery.run_id)
        task = self.get_task(delivery.task_id)
        if run is None or task is None:
            return

        delivered = bool(result.get("delivered"))
        if not delivered:
            run.status = RunStatus.FAILED
            run.error = str(result.get("error") or "delivery failed")
        elif delivery.kind == "follow_up":
            run.status = RunStatus.FOLLOWING_UP
        elif task.follow_up_policy.requires_confirmation:
            run.status = RunStatus.PENDING_CONFIRMATION
        else:
            run.status = RunStatus.SUCCEEDED
        run.finished_at = delivered_at
        run.result = {
            **run.result,
            **result,
            "delivery_id": delivery.id,
            "delivery_status": delivery.status,
            "delivered_at": delivered_at.isoformat(),
        }
        run.error = run.error or result.get("error")
        self.store.save_run(run)

    def _failed_delivery_can_retry(
        self,
        delivery: Delivery,
        *,
        automatic: bool = False,
        max_attempts: int | None = None,
    ) -> bool:
        """判断失败投递是否仍对应一个可重试的 run。"""
        if (
            delivery.status != DeliveryStatus.FAILED
            or delivery.run_id is None
            or delivery.task_id is None
        ):
            return False
        run = self.get_run(delivery.run_id)
        task = self.get_task(delivery.task_id)
        if run is None or task is None or task.status != TaskStatus.ACTIVE:
            return False
        if run.status in {RunStatus.SUCCEEDED, RunStatus.CANCELLED} or run.confirmed_at:
            return False
        if automatic and max_attempts is not None:
            attempts = int(delivery.result.get("auto_retry_attempts", 0))
            if attempts >= max_attempts:
                return False
        return run.result.get("delivery_id") == delivery.id

    def _create_retry_delivery(
        self,
        delivery: Delivery,
        current: datetime,
        *,
        automatic: bool = False,
    ) -> Delivery:
        """创建新的 delivery，保留原失败记录作为审计历史。"""
        run = self.get_run(str(delivery.run_id))
        if run is None:
            raise KeyError(str(delivery.run_id))

        retry_result: dict[str, object] = {
            "retry_of": delivery.id,
            "retry_requested_at": current.isoformat(),
        }
        if automatic:
            retry_result["retry_mode"] = "automatic"
            retry_result["auto_retry_attempts"] = (
                int(delivery.result.get("auto_retry_attempts", 0)) + 1
            )
            self.metrics.increment("auto_retry_created_total")

        retry = Delivery(
            id=f"delivery_{uuid4().hex}",
            run_id=delivery.run_id,
            task_id=delivery.task_id,
            kind=delivery.kind,
            action=delivery.action,
            due_at=delivery.due_at,
            deliver_at=current,
            status=DeliveryStatus.PENDING,
            reason=delivery.reason,
            result=retry_result,
            created_at=current,
            updated_at=current,
        )
        self.store.save_delivery(retry)

        run.status = RunStatus.PENDING_DELIVERY
        run.finished_at = None
        run.error = None
        run.result = {
            **run.result,
            "delivery_id": retry.id,
            "delivery_status": retry.status,
            "retry_of_delivery_id": delivery.id,
            "retry_requested_at": current.isoformat(),
        }
        self.store.save_run(run)
        return retry

    def _auto_retry_failed_deliveries(self, current: datetime) -> list[Delivery]:
        """按配置自动重试失败投递，默认关闭。"""
        if (
            not self.settings.auto_retry_failed_deliveries
            or self.settings.auto_retry_max_attempts <= 0
        ):
            return []
        return self.retry_failed_deliveries(
            now=current,
            automatic=True,
            max_attempts=self.settings.auto_retry_max_attempts,
        )

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
        for follow_up in self.store.list_follow_ups_for_origin(origin_run_id):
            if follow_up.id == exclude_run_id or follow_up.status not in ACTIVE_RUN_STATUSES:
                continue
            follow_up.status = RunStatus.CANCELLED
            follow_up.finished_at = cancelled_at
            follow_up.result = {**follow_up.result, "cancelled_reason": reason}
            self.store.save_run(follow_up)
            self._cancel_deliveries_for_run(follow_up.id, cancelled_at, reason)

    def _cancel_open_runs_for_task(
        self,
        task_id: str,
        cancelled_at: datetime,
        reason: str,
    ) -> None:
        """取消任务下仍在等待确认或跟进的运行记录。"""
        for run in self.store.list_open_runs_for_task(task_id, ACTIVE_RUN_STATUSES):
            run.status = RunStatus.CANCELLED
            run.finished_at = cancelled_at
            run.result = {**run.result, "cancelled_reason": reason}
            self.store.save_run(run)
            self._cancel_deliveries_for_run(run.id, cancelled_at, reason)

    def _last_primary_run_for_task(self, task_id: str) -> Run | None:
        return self.store.last_primary_run_for_task(task_id)

    def _validate_task_contract(self, task: Task) -> None:
        """校验跨字段调度约束。"""
        schedule = task.schedule
        if (
            schedule.kind == "recurring"
            and schedule.anchor == "completion"
            and not task.follow_up_policy.requires_confirmation
        ):
            raise InvalidTaskConfigurationError("completion anchor requires confirmation")

    def _validate_task_schedule_transition(self, previous: Task, updated: Task) -> None:
        """阻止更新后进入缺失完成锚点的调度状态。"""
        if not self._uses_completion_anchor(updated) or self._uses_completion_anchor(previous):
            return

        last_run = self._last_primary_run_for_task(previous.id)
        if last_run is None or last_run.confirmed_at is not None:
            return
        if str(last_run.status) in ACTIVE_RUN_STATUSES:
            return

        raise InvalidTaskConfigurationError(
            "switching to completion anchor requires confirming the latest primary run"
        )

    def _uses_completion_anchor(self, task: Task) -> bool:
        schedule = task.schedule
        return schedule.kind == "recurring" and schedule.anchor == "completion"

    def _idempotency_hash(self, request: TaskCreate) -> str:
        """生成创建请求摘要，用于检测同 key 不同请求。"""
        return dump_json(request.model_dump(mode="json"))

    def _save_notification_from_result(
        self,
        result: dict[str, object],
        run_id: str | None,
        task_id: str | None,
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
