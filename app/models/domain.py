"""Domain models for courses, tasks, availability, plans, and review decisions."""

from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    """Base model that rejects undeclared fields to keep agent data structured."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class ReviewStatus(StrEnum):
    APPROVED = "approved"
    REPLAN_REQUIRED = "replan_required"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PlanStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class CourseCreate(StrictModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=120)
    credit_hours: float = Field(gt=0, le=12)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return " ".join(value.upper().split())


class Course(CourseCreate):
    id: str
    user_id: str
    created_at: datetime


class AcademicTaskCreate(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    course_id: str = Field(min_length=1, max_length=64)
    deadline: datetime
    estimated_hours: float = Field(gt=0, le=200)
    difficulty: int = Field(default=3, ge=1, le=5)
    user_priority: TaskPriority = TaskPriority.MEDIUM


class AcademicTask(AcademicTaskCreate):
    id: str
    user_id: str
    status: TaskStatus = TaskStatus.TODO
    created_at: datetime


class AvailabilityWindowCreate(StrictModel):
    date: date
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def validate_time_range(self) -> "AvailabilityWindowCreate":
        start_minutes = self.start_time.hour * 60 + self.start_time.minute
        end_minutes = self.end_time.hour * 60 + self.end_time.minute
        if end_minutes <= start_minutes:
            raise ValueError("end_time must be after start_time on the same day")
        if end_minutes - start_minutes > 12 * 60:
            raise ValueError("an availability window cannot exceed 12 hours")
        return self

    @property
    def duration_hours(self) -> float:
        start_minutes = self.start_time.hour * 60 + self.start_time.minute
        end_minutes = self.end_time.hour * 60 + self.end_time.minute
        return (end_minutes - start_minutes) / 60


class AvailabilityWindow(AvailabilityWindowCreate):
    id: str
    user_id: str
    created_at: datetime


class AnalyzedTask(StrictModel):
    task_id: str
    urgency_score: float = Field(ge=0, le=100)
    priority_score: float = Field(ge=0, le=100)
    hours_remaining: float = Field(ge=0)
    deadline_risk: str = Field(min_length=1, max_length=80)
    reasoning_summary: str = Field(min_length=1, max_length=500)


class StudySession(StrictModel):
    task_id: str
    course_id: str
    date: date
    start_time: time
    end_time: time
    planned_hours: float = Field(gt=0, le=12)
    rationale: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_session_duration(self) -> "StudySession":
        start_minutes = self.start_time.hour * 60 + self.start_time.minute
        end_minutes = self.end_time.hour * 60 + self.end_time.minute
        if end_minutes <= start_minutes:
            raise ValueError("session end_time must be after start_time")
        calculated = (end_minutes - start_minutes) / 60
        if abs(calculated - self.planned_hours) > 0.02:
            raise ValueError("planned_hours must match start_time/end_time duration")
        return self


class StudyPlan(StrictModel):
    thread_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    status: PlanStatus = PlanStatus.DRAFT
    sessions: list[StudySession] = Field(default_factory=list)
    summary: str = Field(default="", max_length=1000)
    created_at: datetime
    updated_at: datetime

    @property
    def total_hours(self) -> float:
        return round(sum(session.planned_hours for session in self.sessions), 2)


class ReviewResult(StrictModel):
    status: ReviewStatus
    feedback: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class ApprovalDecision(StrictModel):
    decision: ApprovalStatus
    feedback: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_feedback_for_rejection(self) -> "ApprovalDecision":
        if self.decision == ApprovalStatus.REJECTED and not self.feedback:
            raise ValueError("feedback is required when a plan is rejected")
        if self.decision == ApprovalStatus.PENDING:
            raise ValueError("a human decision must be approved or rejected")
        return self


class ToolEvent(StrictModel):
    timestamp: datetime
    thread_id: str
    node: str
    agent: str | None = None
    tool_name: str | None = None
    success: bool
    latency_ms: float = Field(ge=0)
    retry_count: int = Field(default=0, ge=0)
    details: dict[str, Any] = Field(default_factory=dict)
