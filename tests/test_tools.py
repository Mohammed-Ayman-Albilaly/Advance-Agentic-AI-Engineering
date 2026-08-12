from datetime import date, datetime, time, timezone
import sqlite3

import pytest

from app.models import PlanStatus, StudyPlan, StudySession, TaskPriority
from app.persistence import Database
from app.tools import (
    RetryExhaustedError,
    StudyTools,
    TransientToolError,
    execute_with_retry,
)


NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def make_tools(tmp_path):
    db = Database(tmp_path / "tools.sqlite")
    db.initialize()
    return StudyTools(db, clock=lambda: NOW)


def seed_course(tools: StudyTools, user_id="student-1"):
    return tools.add_course(
        user_id, code="CEN 351", name="Signals and Systems", credit_hours=3
    )


def test_real_crud_tools_persist_data(tmp_path) -> None:
    tools = make_tools(tmp_path)
    course = seed_course(tools)
    task = tools.add_task(
        "student-1",
        title="Assignment",
        course_id=course["id"],
        deadline="2026-08-15T20:00:00+00:00",
        estimated_hours=3,
        difficulty=4,
        user_priority="high",
    )
    tools.set_availability(
        "student-1",
        study_date="2026-08-13",
        start_time="18:00",
        end_time="21:00",
    )

    assert tools.get_courses("student-1")[0]["id"] == course["id"]
    assert tools.get_tasks("student-1")[0]["id"] == task["id"]
    assert tools.get_available_hours("student-1")["total_hours"] == 3


def test_cross_user_course_reference_is_blocked_by_database(tmp_path) -> None:
    tools = make_tools(tmp_path)
    course = seed_course(tools, "student-a")

    with pytest.raises(sqlite3.IntegrityError):
        tools.add_task(
            "student-b",
            title="Unauthorized reference",
            course_id=course["id"],
            deadline="2026-08-15T20:00:00+00:00",
            estimated_hours=1,
        )


def test_availability_overlap_is_not_double_counted(tmp_path) -> None:
    tools = make_tools(tmp_path)
    tools.set_availability(
        "student-1", study_date="2026-08-13", start_time="18:00", end_time="21:00"
    )
    tools.set_availability(
        "student-1", study_date="2026-08-13", start_time="20:00", end_time="22:00"
    )

    result = tools.get_available_hours("student-1")
    assert result["total_hours"] == 4
    assert result["hours_by_date"]["2026-08-13"] == 4


def test_priority_analysis_prefers_near_high_priority_task(tmp_path) -> None:
    tools = make_tools(tmp_path)
    course = seed_course(tools)
    task = tools.add_task(
        "student-1",
        title="Urgent exam review",
        course_id=course["id"],
        deadline="2026-08-13T08:00:00+00:00",
        estimated_hours=4,
        difficulty=5,
        user_priority=TaskPriority.CRITICAL,
    )

    analyzed = tools.calculate_task_priority(task)
    assert analyzed["deadline_risk"] == "critical"
    assert analyzed["priority_score"] >= 85
    assert analyzed["hours_remaining"] == 4


def test_weekly_workload_reports_infeasible_capacity(tmp_path) -> None:
    tools = make_tools(tmp_path)
    course = seed_course(tools)
    tools.add_task(
        "student-1",
        title="Large assignment",
        course_id=course["id"],
        deadline="2026-08-14T20:00:00+00:00",
        estimated_hours=6,
    )
    tools.set_availability(
        "student-1", study_date="2026-08-13", start_time="18:00", end_time="20:00"
    )

    workload = tools.calculate_weekly_workload(
        "student-1", start_date="2026-08-12", end_date="2026-08-16"
    )
    assert workload["required_hours"] == 6
    assert workload["available_hours"] == 2
    assert workload["capacity_gap_hours"] == -4
    assert workload["feasible"] is False


def test_deadline_conflict_detects_capacity_shortfall(tmp_path) -> None:
    tools = make_tools(tmp_path)
    course = seed_course(tools)
    tools.add_task(
        "student-1",
        title="Exam preparation",
        course_id=course["id"],
        deadline="2026-08-13T23:00:00+00:00",
        estimated_hours=5,
    )
    tools.set_availability(
        "student-1", study_date="2026-08-13", start_time="18:00", end_time="20:00"
    )

    conflicts = tools.check_deadline_conflicts("student-1")
    assert len(conflicts) == 1
    assert "exceeds available study capacity" in conflicts[0]
    assert "3.0h" in conflicts[0]


def test_plan_capacity_catches_outside_window_and_overlap(tmp_path) -> None:
    tools = make_tools(tmp_path)
    course = seed_course(tools)
    task = tools.add_task(
        "student-1",
        title="Project",
        course_id=course["id"],
        deadline="2026-08-15T20:00:00+00:00",
        estimated_hours=4,
    )
    tools.set_availability(
        "student-1", study_date="2026-08-13", start_time="18:00", end_time="21:00"
    )
    sessions = [
        {
            "task_id": task["id"],
            "course_id": course["id"],
            "date": "2026-08-13",
            "start_time": "18:00",
            "end_time": "20:00",
            "planned_hours": 2,
            "rationale": "Urgent task",
        },
        {
            "task_id": task["id"],
            "course_id": course["id"],
            "date": "2026-08-13",
            "start_time": "19:30",
            "end_time": "21:30",
            "planned_hours": 2,
            "rationale": "Continue work",
        },
    ]

    result = tools.validate_plan_capacity("student-1", sessions=sessions)
    assert result["valid"] is False
    assert any("outside declared availability" in issue for issue in result["issues"])
    assert any("overlapping study sessions" in issue for issue in result["issues"])


def test_plan_save_load_is_scoped_to_user(tmp_path) -> None:
    tools = make_tools(tmp_path)
    now = NOW
    plan = StudyPlan(
        thread_id="thread-1",
        user_id="student-1",
        status=PlanStatus.AWAITING_APPROVAL,
        sessions=[],
        summary="Awaiting approval",
        created_at=now,
        updated_at=now,
    )
    tools.save_study_plan(plan)

    assert tools.load_study_plan(thread_id="thread-1", user_id="student-1") is not None
    assert tools.load_study_plan(thread_id="thread-1", user_id="student-2") is None


def test_transient_failure_retries_and_then_succeeds() -> None:
    calls = {"count": 0}

    def flaky_tool():
        calls["count"] += 1
        if calls["count"] == 1:
            raise TransientToolError("simulated temporary database lock")
        return {"status": "ok"}

    result = execute_with_retry(flaky_tool, max_attempts=2)
    assert result.value == {"status": "ok"}
    assert result.attempts == 2
    assert calls["count"] == 2


def test_retry_exhaustion_is_explicit() -> None:
    def always_fails():
        raise TransientToolError("still unavailable")

    with pytest.raises(RetryExhaustedError, match="after 2 attempts"):
        execute_with_retry(always_fails, max_attempts=2)


def test_deadline_conflict_does_not_count_availability_after_deadline(tmp_path) -> None:
    tools = make_tools(tmp_path)
    course = seed_course(tools)
    tools.add_task(
        "student-1",
        title="Noon deadline",
        course_id=course["id"],
        deadline="2026-08-13T12:00:00+00:00",
        estimated_hours=2,
    )
    # This time is on the same date, but too late to help with the noon deadline.
    tools.set_availability(
        "student-1", study_date="2026-08-13", start_time="18:00", end_time="21:00"
    )

    conflicts = tools.check_deadline_conflicts("student-1")
    assert len(conflicts) == 1
    assert "2.0h" in conflicts[0]


def test_deadline_conflict_does_not_count_past_availability_today(tmp_path) -> None:
    tools = make_tools(tmp_path)
    course = seed_course(tools)
    tools.add_task(
        "student-1",
        title="Tonight deadline",
        course_id=course["id"],
        deadline="2026-08-12T20:00:00+00:00",
        estimated_hours=2,
    )
    # NOW is 12:00. Only one hour (12:00-13:00) remains usable here.
    tools.set_availability(
        "student-1", study_date="2026-08-12", start_time="10:00", end_time="13:00"
    )

    conflicts = tools.check_deadline_conflicts("student-1")
    assert len(conflicts) == 1
    assert "1.0h" in conflicts[0]


def test_get_availability_windows_returns_persisted_windows(tmp_path) -> None:
    tools = make_tools(tmp_path)
    tools.set_availability(
        "student-1", study_date="2026-08-13", start_time="18:00", end_time="21:00"
    )
    windows = tools.get_availability_windows("student-1")
    assert len(windows) == 1
    assert windows[0]["date"] == "2026-08-13"
    assert windows[0]["start_time"] == "18:00:00"
