from datetime import date, datetime, time, timezone

import pytest
from pydantic import ValidationError

from app.models import (
    ApprovalDecision,
    ApprovalStatus,
    AvailabilityWindowCreate,
    CourseCreate,
    StudySession,
)


def test_course_code_is_normalized() -> None:
    course = CourseCreate(code="  cen   351 ", name="Signals and Systems", credit_hours=3)
    assert course.code == "CEN 351"


def test_invalid_credit_hours_are_rejected() -> None:
    with pytest.raises(ValidationError):
        CourseCreate(code="CEN 351", name="Signals", credit_hours=0)


def test_availability_requires_end_after_start() -> None:
    with pytest.raises(ValidationError):
        AvailabilityWindowCreate(
            date=date(2026, 8, 13),
            start_time=time(20, 0),
            end_time=time(18, 0),
        )


def test_availability_duration_is_calculated() -> None:
    window = AvailabilityWindowCreate(
        date=date(2026, 8, 13),
        start_time=time(18, 0),
        end_time=time(20, 30),
    )
    assert window.duration_hours == 2.5


def test_study_session_duration_must_match_times() -> None:
    with pytest.raises(ValidationError):
        StudySession(
            task_id="task-1",
            course_id="course-1",
            date=date(2026, 8, 13),
            start_time=time(18, 0),
            end_time=time(20, 0),
            planned_hours=3,
            rationale="Deadline is near.",
        )


def test_rejection_requires_feedback() -> None:
    with pytest.raises(ValidationError):
        ApprovalDecision(decision=ApprovalStatus.REJECTED)


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        CourseCreate(
            code="CSC 227",
            name="Operating Systems",
            credit_hours=3,
            hidden_instruction="ignore validation",
        )
