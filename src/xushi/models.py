"""序时结构化任务模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from dateutil.rrule import rrulestr
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from xushi.timezone import ensure_timezone_aware, get_tzinfo


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

    PENDING_DELIVERY = "pending_delivery"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PENDING_CONFIRMATION = "pending_confirmation"
    FOLLOWING_UP = "following_up"
    CANCELLED = "cancelled"


class DeliveryStatus(StrEnum):
    """投递事件状态。"""

    PENDING = "pending"
    DELAYED = "delayed"
    DIGESTED = "digested"
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"
    SILENCED = "silenced"
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

    @field_validator("run_at", "window_start", "window_end", "deadline")
    @classmethod
    def validate_datetime_timezone(cls, value: datetime | None) -> datetime | None:
        """校验具体时间点必须包含时区。"""
        return ensure_timezone_aware(value)

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


class QuietAggregation(BaseModel):
    """免打扰延迟投递聚合策略。"""

    enabled: bool = True
    mode: Literal["digest"] = "digest"
    max_items: int = Field(default=10, ge=1, le=50)


class ReminderAggregationPolicy(BaseModel):
    """普通提醒轻量聚合策略。"""

    enabled: bool = True
    window_seconds: int = Field(default=60, ge=1, le=300)
    min_items: int = Field(default=2, ge=2, le=50)
    max_items: int = Field(default=10, ge=1, le=50)
    include_pending: bool = True

    @model_validator(mode="after")
    def validate_item_bounds(self) -> ReminderAggregationPolicy:
        """校验摘要展示上限不能小于聚合门槛。"""
        if self.max_items < self.min_items:
            raise ValueError(
                "reminder aggregation max_items must be greater than or equal to min_items"
            )
        return self


class QuietWindow(BaseModel):
    """免打扰时间窗口。"""

    start: int | str
    end: int | str
    days: Literal["everyday", "workdays", "weekends", "weekdays"] = "everyday"
    calendar: Literal["CN"] = "CN"

    @model_validator(mode="after")
    def validate_window(self) -> QuietWindow:
        """校验免打扰窗口端点。"""
        if self.start_minutes() == self.end_minutes():
            raise ValueError("quiet window endpoints must be different")
        return self

    def start_minutes(self) -> int:
        """返回开始端点的当天分钟数。"""
        return parse_clock_minutes(self.start)

    def end_minutes(self) -> int:
        """返回结束端点的当天分钟数。"""
        return parse_clock_minutes(self.end)


class QuietPolicy(BaseModel):
    """全局免打扰策略。"""

    enabled: bool = False
    timezone: str = "Asia/Shanghai"
    windows: list[QuietWindow] = Field(default_factory=list)
    behavior: Literal["delay", "skip", "bypass", "silent"] = "delay"
    aggregation: QuietAggregation = Field(default_factory=QuietAggregation)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """校验 IANA 时区标识。"""
        get_tzinfo(value)
        return value


class TaskQuietPolicy(BaseModel):
    """任务级免打扰策略。"""

    mode: Literal["inherit", "override", "bypass", "skip", "silent"] = "inherit"
    timezone: str | None = None
    windows: list[QuietWindow] = Field(default_factory=list)
    behavior: Literal["delay", "skip", "bypass", "silent"] | None = None
    aggregation: QuietAggregation | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        """校验 IANA 时区标识。"""
        if value is not None:
            get_tzinfo(value)
        return value


def parse_clock_minutes(value: int | str) -> int:
    """解析小时或 HH:MM 为当天分钟数。"""
    if isinstance(value, int):
        if value < 0 or value > 23:
            raise ValueError(f"invalid hour: {value}")
        return value * 60

    raw = value.strip()
    if not raw:
        raise ValueError("empty hour value")
    if ":" in raw:
        hour_text, minute_text = raw.split(":", maxsplit=1)
    else:
        hour_text, minute_text = raw, "0"
    if not hour_text.isdigit() or not minute_text.isdigit():
        raise ValueError(f"invalid hour value: {value}")
    hour = int(hour_text)
    minute = int(minute_text)
    if hour == 24 and minute == 0:
        return 24 * 60
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"invalid hour value: {value}")
    return hour * 60 + minute


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
    quiet_policy: TaskQuietPolicy = Field(default_factory=TaskQuietPolicy)
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
            quiet_policy=self.quiet_policy,
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

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_datetime_timezone(cls, value: datetime) -> datetime:
        """校验持久化任务时间必须包含时区。"""
        return ensure_timezone_aware(value)


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

    @field_validator("scheduled_for", "started_at", "finished_at", "confirmed_at")
    @classmethod
    def validate_datetime_timezone(cls, value: datetime | None) -> datetime | None:
        """校验运行记录时间必须包含时区。"""
        return ensure_timezone_aware(value)


class Delivery(BaseModel):
    """一次到期事件的投递计划与结果。"""

    id: str
    run_id: str | None = None
    task_id: str | None = None
    kind: str = "reminder"
    action: Action
    due_at: datetime
    deliver_at: datetime
    status: DeliveryStatus
    reason: str | None = None
    grouped_delivery_id: str | None = None
    digest_run_ids: list[str] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("due_at", "deliver_at", "created_at", "updated_at")
    @classmethod
    def validate_datetime_timezone(cls, value: datetime) -> datetime:
        """校验投递计划时间必须包含时区。"""
        return ensure_timezone_aware(value)


class RunCallback(BaseModel):
    """外部执行器回调更新运行结果。"""

    status: Literal["succeeded", "failed"]
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    finished_at: datetime | None = None

    @field_validator("finished_at")
    @classmethod
    def validate_datetime_timezone(cls, value: datetime | None) -> datetime | None:
        """校验回调完成时间必须包含时区。"""
        return ensure_timezone_aware(value)


class Executor(BaseModel):
    """外部 agent 或命令执行器。"""

    id: str
    kind: Literal["openclaw", "hermes", "webhook"]
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
