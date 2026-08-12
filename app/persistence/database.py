"""SQLite persistence layer for UniFlow AI application data.

LangGraph workflow checkpoints will use a separate SQLite database in the graph
layer.  This module stores domain data such as courses, tasks, availability, and
approved/proposed plans.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from app.models import (
    AcademicTask,
    AcademicTaskCreate,
    AvailabilityWindow,
    AvailabilityWindowCreate,
    Course,
    CourseCreate,
    StudyPlan,
    TaskStatus,
)


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    credit_hours REAL NOT NULL CHECK (credit_hours > 0),
    created_at TEXT NOT NULL,
    UNIQUE(user_id, code),
    UNIQUE(user_id, id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    title TEXT NOT NULL,
    deadline TEXT NOT NULL,
    estimated_hours REAL NOT NULL CHECK (estimated_hours > 0),
    difficulty INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
    user_priority TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id, course_id) REFERENCES courses(user_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tasks_user_deadline
ON tasks(user_id, deadline);

CREATE INDEX IF NOT EXISTS idx_tasks_course
ON tasks(course_id);

CREATE TABLE IF NOT EXISTS availability_windows (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    study_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, study_date, start_time, end_time)
);

CREATE INDEX IF NOT EXISTS idx_availability_user_date
ON availability_windows(user_id, study_date);

CREATE TABLE IF NOT EXISTS study_plans (
    thread_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_study_plans_user
ON study_plans(user_id, updated_at);
"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Database:
    """Small explicit repository around SQLite with validated domain models."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)

    def health_check(self) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT 1 AS ok").fetchone()
            return bool(row and row["ok"] == 1)

    def create_course(self, user_id: str, payload: CourseCreate) -> Course:
        course = Course(
            id=str(uuid4()),
            user_id=user_id,
            created_at=_utc_now(),
            **payload.model_dump(),
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO courses(id, user_id, code, name, credit_hours, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    course.id,
                    course.user_id,
                    course.code,
                    course.name,
                    course.credit_hours,
                    course.created_at.isoformat(),
                ),
            )
        return course

    def list_courses(self, user_id: str) -> list[Course]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, code, name, credit_hours, created_at
                FROM courses
                WHERE user_id = ?
                ORDER BY code ASC
                """,
                (user_id,),
            ).fetchall()
        return [Course.model_validate(dict(row)) for row in rows]

    def create_task(self, user_id: str, payload: AcademicTaskCreate) -> AcademicTask:
        task = AcademicTask(
            id=str(uuid4()),
            user_id=user_id,
            status=TaskStatus.TODO,
            created_at=_utc_now(),
            **payload.model_dump(),
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks(
                    id, user_id, course_id, title, deadline, estimated_hours,
                    difficulty, user_priority, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.user_id,
                    task.course_id,
                    task.title,
                    task.deadline.isoformat(),
                    task.estimated_hours,
                    task.difficulty,
                    task.user_priority.value,
                    task.status.value,
                    task.created_at.isoformat(),
                ),
            )
        return task

    def list_tasks(self, user_id: str) -> list[AcademicTask]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, course_id, title, deadline, estimated_hours,
                       difficulty, user_priority, status, created_at
                FROM tasks
                WHERE user_id = ?
                ORDER BY deadline ASC
                """,
                (user_id,),
            ).fetchall()
        return [AcademicTask.model_validate(dict(row)) for row in rows]

    def update_task_status(
        self, user_id: str, task_id: str, status: TaskStatus
    ) -> AcademicTask | None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE tasks SET status = ? WHERE id = ? AND user_id = ?",
                (status.value, task_id, user_id),
            )
            row = conn.execute(
                """
                SELECT id, user_id, course_id, title, deadline, estimated_hours,
                       difficulty, user_priority, status, created_at
                FROM tasks
                WHERE id = ? AND user_id = ?
                """,
                (task_id, user_id),
            ).fetchone()
        return AcademicTask.model_validate(dict(row)) if row else None

    def add_availability(
        self, user_id: str, payload: AvailabilityWindowCreate
    ) -> AvailabilityWindow:
        window = AvailabilityWindow(
            id=str(uuid4()),
            user_id=user_id,
            created_at=_utc_now(),
            **payload.model_dump(),
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO availability_windows(
                    id, user_id, study_date, start_time, end_time, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    window.id,
                    window.user_id,
                    window.date.isoformat(),
                    window.start_time.isoformat(),
                    window.end_time.isoformat(),
                    window.created_at.isoformat(),
                ),
            )
        return window

    def list_availability(self, user_id: str) -> list[AvailabilityWindow]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, study_date AS date, start_time, end_time, created_at
                FROM availability_windows
                WHERE user_id = ?
                ORDER BY study_date ASC, start_time ASC
                """,
                (user_id,),
            ).fetchall()
        return [AvailabilityWindow.model_validate(dict(row)) for row in rows]

    def save_plan(self, plan: StudyPlan) -> None:
        payload = plan.model_dump(mode="json")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO study_plans(
                    thread_id, user_id, status, plan_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    status = excluded.status,
                    plan_json = excluded.plan_json,
                    updated_at = excluded.updated_at
                """,
                (
                    plan.thread_id,
                    plan.user_id,
                    plan.status.value,
                    json.dumps(payload, ensure_ascii=False),
                    plan.created_at.isoformat(),
                    plan.updated_at.isoformat(),
                ),
            )

    def load_plan(self, thread_id: str, user_id: str | None = None) -> StudyPlan | None:
        with self.connect() as conn:
            if user_id is None:
                row = conn.execute(
                    "SELECT plan_json FROM study_plans WHERE thread_id = ?",
                    (thread_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT plan_json FROM study_plans WHERE thread_id = ? AND user_id = ?",
                    (thread_id, user_id),
                ).fetchone()
        if not row:
            return None
        return StudyPlan.model_validate(json.loads(row["plan_json"]))
