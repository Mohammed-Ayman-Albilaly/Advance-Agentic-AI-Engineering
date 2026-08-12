from datetime import date, datetime, time, timezone

from app.models import (
    AcademicTaskCreate,
    AvailabilityWindowCreate,
    CourseCreate,
    PlanStatus,
    StudyPlan,
    StudySession,
    TaskPriority,
    TaskStatus,
)
from app.persistence import Database


def make_db(tmp_path):
    db = Database(tmp_path / "uniflow-test.sqlite")
    db.initialize()
    return db


def test_database_initializes_and_is_healthy(tmp_path) -> None:
    db = make_db(tmp_path)
    assert db.health_check() is True


def test_course_task_and_availability_persist(tmp_path) -> None:
    db = make_db(tmp_path)
    user_id = "student-1"

    course = db.create_course(
        user_id,
        CourseCreate(code="CEN 351", name="Signals and Systems", credit_hours=3),
    )
    task = db.create_task(
        user_id,
        AcademicTaskCreate(
            title="Assignment 1",
            course_id=course.id,
            deadline=datetime(2026, 8, 15, 23, 59, tzinfo=timezone.utc),
            estimated_hours=3,
            difficulty=4,
            user_priority=TaskPriority.HIGH,
        ),
    )
    db.add_availability(
        user_id,
        AvailabilityWindowCreate(
            date=date(2026, 8, 13),
            start_time=time(18, 0),
            end_time=time(21, 0),
        ),
    )

    # New repository instance proves data was stored in the file, not in memory.
    reopened = Database(db.path)
    reopened.initialize()

    courses = reopened.list_courses(user_id)
    tasks = reopened.list_tasks(user_id)
    windows = reopened.list_availability(user_id)

    assert courses[0].id == course.id
    assert tasks[0].id == task.id
    assert tasks[0].status == TaskStatus.TODO
    assert windows[0].duration_hours == 3


def test_foreign_key_blocks_task_for_unknown_course(tmp_path) -> None:
    import sqlite3
    import pytest

    db = make_db(tmp_path)
    payload = AcademicTaskCreate(
        title="Impossible task",
        course_id="missing-course",
        deadline=datetime(2026, 8, 15, 23, 59, tzinfo=timezone.utc),
        estimated_hours=2,
    )

    with pytest.raises(sqlite3.IntegrityError):
        db.create_task("student-1", payload)


def test_task_status_update_is_persisted(tmp_path) -> None:
    db = make_db(tmp_path)
    user_id = "student-1"
    course = db.create_course(
        user_id,
        CourseCreate(code="EE 310", name="Microelectronics", credit_hours=4),
    )
    task = db.create_task(
        user_id,
        AcademicTaskCreate(
            title="Quiz review",
            course_id=course.id,
            deadline=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
            estimated_hours=2,
        ),
    )

    updated = db.update_task_status(user_id, task.id, TaskStatus.DONE)
    assert updated is not None
    assert updated.status == TaskStatus.DONE
    assert Database(db.path).list_tasks(user_id)[0].status == TaskStatus.DONE


def test_plan_round_trip(tmp_path) -> None:
    db = make_db(tmp_path)
    now = datetime.now(timezone.utc)
    plan = StudyPlan(
        thread_id="thread-001",
        user_id="student-1",
        status=PlanStatus.AWAITING_APPROVAL,
        sessions=[
            StudySession(
                task_id="task-1",
                course_id="course-1",
                date=date(2026, 8, 13),
                start_time=time(18, 0),
                end_time=time(20, 0),
                planned_hours=2,
                rationale="High-priority task with an approaching deadline.",
            )
        ],
        summary="Initial proposed plan.",
        created_at=now,
        updated_at=now,
    )

    db.save_plan(plan)
    loaded = Database(db.path).load_plan("thread-001")

    assert loaded is not None
    assert loaded.thread_id == plan.thread_id
    assert loaded.total_hours == 2
    assert loaded.status == PlanStatus.AWAITING_APPROVAL
