"""Pydantic request/response schemas for the FastAPI boundary."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import Field

from app.models import ApprovalStatus, StrictModel, TaskPriority, TaskStatus


class UserScopedRequest(StrictModel):
    user_id: str = Field(min_length=1, max_length=128)


class CourseRequest(UserScopedRequest):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=120)
    credit_hours: float = Field(gt=0, le=12)


class TaskRequest(UserScopedRequest):
    title: str = Field(min_length=1, max_length=160)
    course_id: str = Field(min_length=1, max_length=64)
    deadline: datetime
    estimated_hours: float = Field(gt=0, le=200)
    difficulty: int = Field(default=3, ge=1, le=5)
    user_priority: TaskPriority = TaskPriority.MEDIUM


class TaskStatusRequest(UserScopedRequest):
    status: TaskStatus


class AvailabilityRequest(UserScopedRequest):
    date: date
    start_time: time
    end_time: time


class WorkflowStartRequest(UserScopedRequest):
    user_request: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = Field(default=None, min_length=1, max_length=128)


class WorkflowResumeRequest(UserScopedRequest):
    decision: ApprovalStatus
    feedback: str | None = Field(default=None, max_length=1000)


class WorkflowResponse(StrictModel):
    thread_id: str
    status: str
    state: dict[str, Any] = Field(default_factory=dict)
    interrupt: dict[str, Any] | None = None
