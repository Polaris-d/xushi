"""序时结构化任务模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from dateutil.rrule import rrulestr
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from xushi.timezone import get_tzinfo


class MissedPolicy(StrEnum):
    """错过触发时的处理策略。"""

    SKIP = "skip"
    CATCH_UP_LATEST = "catch_up_latest"
    CATCH_UP_ALL = "catch_up_all"
    FAIL = "fail"
    ASK_RESCHEDULE = "ask_reschedule"


class TaskStatus(StrEnum):
    """任务生命周期状态。"""

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"
    COMPLETED = "completed"


class RunStatus(StrEnum):
    """运行记录状态。"""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PENDING_CONFIRMATION = "pending_confirmation"
    FOLLOWING_UP = "following_up"
    CANCELLED = "cancelled"


class Schedule(BaseModel):
    """结构化时间契约。"""

    kind: Literal["one_shot", "recurring", "window", "deadline", "floating", "asap"]
    timezone: str
    run_at: datetime | None = None
    rrule: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    deadline: datetime | None = None
    duration: str | None = None
    expiry: str | None = None
    missed_policy: MissedPolicy = MissedPolicy.CATCH_UP_LATEST
    anchor: Literal["calendar", "completion"] = "calendar"
    calendar_policy: Literal["natural_day", "workday", "custom"] = "natural_day"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """校验 IANA 时区标识。"""
        get_tzinfo(value)
        return value

    @model_validator(mode="after")
    def validate_schedule_shape(self) -> Schedule:
        """校验不同任务类型的必要字段。"""
        if self.kind == "one_shot" and self.run_at is None:
            raise ValueError("one_shot schedule requires run_at")
        if self.kind == "recurring":
            if self.run_at is None:
                raise ValueError("recurring schedule requires run_at")
            if not self.rrule:
                raise ValueError("recurring schedule requires rrule")
            rrulestr(self.rrule, dtstart=self.run_at)
        if self.kind == "window" and (self.window_start is None or self.window_end is None):
            raise ValueError("window schedule requires window_start and window_end")
        if self.kind == "deadline" and self.deadline is None:
            raise ValueError("deadline schedule requires deadline")
        return self


class FollowUpPolicy(BaseModel):
    """未完成任务跟进策略。"""

    requires_confirmation: bool = False
    grace_period: str = "PT0S"
    interval: str = "PT10M"
    max_attempts: int = 0
    ask_reschedule_on_timeout: bool = False
    escalation_channels: list[str] = Field(default_factory=list)


class Action(BaseModel):
    """任务触发动作。"""

    type: Literal["reminder", "agent"]
    executor_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskCreate(BaseModel):
    """创建任务请求。"""

    title: str
    description: str | None = None
    schedule: Schedule
    action: Action
    follow_up_policy: FollowUpPolicy = Field(default_factory=FollowUpPolicy)
    tags: list[str] = Field(default_factory=list)
    created_by: Literal["user", "agent", "api"] = "api"
    idempotency_key: str | None = None

    def to_task(self, task_id: str | None = None) -> Task:
        """转换为持久化任务。"""
        now = datetime.now(tz=get_tzinfo(self.schedule.timezone))
        return Task(
            id=task_id or f"task_{uuid4().hex}",
            title=self.title,
            description=self.description,
            schedule=self.schedule,
            action=self.action,
            follow_up_policy=self.follow_up_policy,
            tags=self.tags,
            created_by=self.created_by,
            idempotency_key=self.idempotency_key,
            status=TaskStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )


class Task(TaskCreate):
    """持久化任务。"""

    id: str
    status: TaskStatus = TaskStatus.ACTIVE
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(use_enum_values=True)


class TaskPatch(BaseModel):
    """更新任务请求。"""

    title: str | None = None
    description: str | None = None
    schedule: Schedule | None = None
    action: Action | None = None
    follow_up_policy: FollowUpPolicy | None = None
    status: TaskStatus | None = None
    tags: list[str] | None = None


class Run(BaseModel):
    """任务运行记录。"""

    id: str
    task_id: str
    origin_run_id: str | None = None
    scheduled_for: datetime
    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus
    attempt: int = 1
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    follow_up_attempts: int = 0
    confirmed_at: datetime | None = None

    model_config = ConfigDict(use_enum_values=True)


class RunCallback(BaseModel):
    """外部执行器回调更新运行结果。"""

    status: Literal["succeeded", "failed"]
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    finished_at: datetime | None = None


class Executor(BaseModel):
    """外部 agent 或命令执行器。"""

    id: str
    kind: Literal["openclaw", "hermes", "webhook"]
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
