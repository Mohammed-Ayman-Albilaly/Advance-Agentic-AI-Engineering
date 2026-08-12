"""Real domain tools used by UniFlow AI agents.

These functions execute validated Python logic and SQLite operations. They are
not prompt-only simulations; graph nodes and LLM tool adapters will call this
service directly.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Iterable

from pydantic import TypeAdapter

from app.models import (
    AcademicTask,
    AcademicTaskCreate,
    AnalyzedTask,
    AvailabilityWindow,
    AvailabilityWindowCreate,
    CourseCreate,
    StudyPlan,
    StudySession,
    TaskPriority,
    TaskStatus,
)
from app.persistence import Database
from app.tools.runtime import ToolExecutionError


_PRIORITY_WEIGHT: dict[TaskPriority, float] = {
    TaskPriority.LOW: 5.0,
    TaskPriority.MEDIUM: 12.0,
    TaskPriority.HIGH: 20.0,
    TaskPriority.CRITICAL: 25.0,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _overlap_hours(
    left_start: time, left_end: time, right_start: time, right_end: time
) -> float:
    start = max(_minutes(left_start), _minutes(right_start))
    end = min(_minutes(left_end), _minutes(right_end))
    return max(0, end - start) / 60


def _merged_hours(windows: Iterable[AvailabilityWindow]) -> float:
    """Count availability capacity without double-counting overlapping windows."""

    by_date: dict[date, list[tuple[int, int]]] = defaultdict(list)
    for window in windows:
        by_date[window.date].append((_minutes(window.start_time), _minutes(window.end_time)))

    total_minutes = 0
    for intervals in by_date.values():
        intervals.sort()
        current_start, current_end = intervals[0]
        for start, end in intervals[1:]:
            if start <= current_end:
                current_end = max(current_end, end)
            else:
                total_minutes += current_end - current_start
                current_start, current_end = start, end
        total_minutes += current_end - current_start
    return round(total_minutes / 60, 2)


def _capacity_between(
    windows: Iterable[AvailabilityWindow],
    *,
    start: datetime,
    end: datetime,
) -> float:
    """Return merged availability that actually falls inside a datetime range.

    Availability windows are local wall-clock values. The graph/API will keep them
    in the same scheduling timezone as task deadlines. Clipping here prevents
    counting past hours today or hours that occur after a deadline on its date.
    """

    if end <= start:
        return 0.0

    clipped: dict[date, list[tuple[int, int]]] = defaultdict(list)
    for window in windows:
        if window.date < start.date() or window.date > end.date():
            continue
        window_start = _minutes(window.start_time)
        window_end = _minutes(window.end_time)
        if window.date == start.date():
            window_start = max(window_start, start.hour * 60 + start.minute)
        if window.date == end.date():
            window_end = min(window_end, end.hour * 60 + end.minute)
        if window_end > window_start:
            clipped[window.date].append((window_start, window_end))

    total_minutes = 0
    for intervals in clipped.values():
        intervals.sort()
        current_start, current_end = intervals[0]
        for interval_start, interval_end in intervals[1:]:
            if interval_start <= current_end:
                current_end = max(current_end, interval_end)
            else:
                total_minutes += current_end - current_start
                current_start, current_end = interval_start, interval_end
        total_minutes += current_end - current_start
    return round(total_minutes / 60, 2)


class StudyTools:
    """Validated real tools backed by the project SQLite repository."""

    def __init__(
        self,
        database: Database,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.database = database
        self.clock = clock

    def add_course(
        self, user_id: str, *, code: str, name: str, credit_hours: float
    ) -> dict[str, Any]:
        course = self.database.create_course(
            user_id,
            CourseCreate(code=code, name=name, credit_hours=credit_hours),
        )
        return course.model_dump(mode="json")

    def get_courses(self, user_id: str) -> list[dict[str, Any]]:
        return [course.model_dump(mode="json") for course in self.database.list_courses(user_id)]

    def add_task(
        self,
        user_id: str,
        *,
        title: str,
        course_id: str,
        deadline: datetime | str,
        estimated_hours: float,
        difficulty: int = 3,
        user_priority: TaskPriority | str = TaskPriority.MEDIUM,
    ) -> dict[str, Any]:
        if isinstance(deadline, str):
            deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        deadline = _ensure_aware(deadline)
        priority = TaskPriority(user_priority)
        task = self.database.create_task(
            user_id,
            AcademicTaskCreate(
                title=title,
                course_id=course_id,
                deadline=deadline,
                estimated_hours=estimated_hours,
                difficulty=difficulty,
                user_priority=priority,
            ),
        )
        return task.model_dump(mode="json")

    def get_tasks(
        self, user_id: str, *, include_done: bool = True
    ) -> list[dict[str, Any]]:
        tasks = self.database.list_tasks(user_id)
        if not include_done:
            tasks = [task for task in tasks if task.status != TaskStatus.DONE]
        return [task.model_dump(mode="json") for task in tasks]

    def update_task_status(
        self, user_id: str, *, task_id: str, status: TaskStatus | str
    ) -> dict[str, Any]:
        updated = self.database.update_task_status(user_id, task_id, TaskStatus(status))
        if updated is None:
            raise ToolExecutionError("task was not found for this user")
        return updated.model_dump(mode="json")

    def set_availability(
        self,
        user_id: str,
        *,
        study_date: date | str,
        start_time: time | str,
        end_time: time | str,
    ) -> dict[str, Any]:
        if isinstance(study_date, str):
            study_date = date.fromisoformat(study_date)
        if isinstance(start_time, str):
            start_time = time.fromisoformat(start_time)
        if isinstance(end_time, str):
            end_time = time.fromisoformat(end_time)
        window = self.database.add_availability(
            user_id,
            AvailabilityWindowCreate(
                date=study_date, start_time=start_time, end_time=end_time
            ),
        )
        return window.model_dump(mode="json")

    def get_available_hours(
        self,
        user_id: str,
        *,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
    ) -> dict[str, Any]:
        if isinstance(start_date, str):
            start_date = date.fromisoformat(start_date)
        if isinstance(end_date, str):
            end_date = date.fromisoformat(end_date)
        if start_date and end_date and end_date < start_date:
            raise ValueError("end_date cannot be before start_date")

        windows = self.database.list_availability(user_id)
        filtered = [
            window
            for window in windows
            if (start_date is None or window.date >= start_date)
            and (end_date is None or window.date <= end_date)
        ]
        per_day: dict[str, float] = {}
        for day in sorted({window.date for window in filtered}):
            per_day[day.isoformat()] = _merged_hours(
                [window for window in filtered if window.date == day]
            )
        return {
            "total_hours": _merged_hours(filtered),
            "hours_by_date": per_day,
            "window_count": len(filtered),
        }

    def get_availability_windows(self, user_id: str) -> list[dict[str, Any]]:
        """Return persisted availability windows for planning agents."""
        return [
            window.model_dump(mode="json")
            for window in self.database.list_availability(user_id)
        ]

    def calculate_task_priority(
        self,
        task: AcademicTask | dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if isinstance(task, dict):
            task = AcademicTask.model_validate(task)
        now = _ensure_aware(now or self.clock())
        deadline = _ensure_aware(task.deadline)
        hours_until_deadline = (deadline - now).total_seconds() / 3600

        if task.status == TaskStatus.DONE:
            analyzed = AnalyzedTask(
                task_id=task.id,
                urgency_score=0,
                priority_score=0,
                hours_remaining=0,
                deadline_risk="completed",
                reasoning_summary="Task is already completed.",
            )
            return analyzed.model_dump(mode="json")

        if hours_until_deadline <= 0:
            urgency = 40.0
            risk = "overdue"
        elif hours_until_deadline <= 24:
            urgency = 38.0
            risk = "critical"
        elif hours_until_deadline <= 72:
            urgency = 32.0
            risk = "high"
        elif hours_until_deadline <= 7 * 24:
            urgency = 24.0
            risk = "medium"
        elif hours_until_deadline <= 14 * 24:
            urgency = 14.0
            risk = "low"
        else:
            urgency = 6.0
            risk = "normal"

        difficulty_component = task.difficulty / 5 * 20
        effort_component = min(task.estimated_hours / 10, 1.0) * 15
        user_component = _PRIORITY_WEIGHT[task.user_priority]
        score = min(100.0, urgency + difficulty_component + effort_component + user_component)

        analyzed = AnalyzedTask(
            task_id=task.id,
            urgency_score=round(urgency / 40 * 100, 2),
            priority_score=round(score, 2),
            hours_remaining=task.estimated_hours,
            deadline_risk=risk,
            reasoning_summary=(
                f"Risk={risk}; deadline is {round(hours_until_deadline, 1)} hours away; "
                f"difficulty={task.difficulty}/5; estimated effort={task.estimated_hours}h; "
                f"user priority={task.user_priority.value}."
            ),
        )
        return analyzed.model_dump(mode="json")

    def calculate_weekly_workload(
        self,
        user_id: str,
        *,
        start_date: date | str,
        end_date: date | str,
    ) -> dict[str, Any]:
        if isinstance(start_date, str):
            start_date = date.fromisoformat(start_date)
        if isinstance(end_date, str):
            end_date = date.fromisoformat(end_date)
        if end_date < start_date:
            raise ValueError("end_date cannot be before start_date")

        tasks = [
            task
            for task in self.database.list_tasks(user_id)
            if task.status != TaskStatus.DONE
            and start_date <= _ensure_aware(task.deadline).date() <= end_date
        ]
        required = round(sum(task.estimated_hours for task in tasks), 2)
        availability = self.get_available_hours(
            user_id, start_date=start_date, end_date=end_date
        )
        available = float(availability["total_hours"])
        gap = round(available - required, 2)
        utilization = round(required / available, 3) if available else None
        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "task_count": len(tasks),
            "required_hours": required,
            "available_hours": available,
            "capacity_gap_hours": gap,
            "utilization_ratio": utilization,
            "feasible": required <= available,
        }

    def check_deadline_conflicts(
        self,
        user_id: str,
        *,
        now: datetime | None = None,
    ) -> list[str]:
        """Detect tasks whose cumulative required hours exceed capacity before deadline."""

        now = _ensure_aware(now or self.clock())
        pending = [
            task
            for task in self.database.list_tasks(user_id)
            if task.status != TaskStatus.DONE
        ]
        pending.sort(key=lambda task: _ensure_aware(task.deadline))
        windows = self.database.list_availability(user_id)

        conflicts: list[str] = []
        cumulative_required = 0.0
        for task in pending:
            deadline = _ensure_aware(task.deadline)
            cumulative_required += task.estimated_hours
            if deadline <= now:
                conflicts.append(f"{task.title}: deadline has already passed")
                continue
            capacity = _capacity_between(windows, start=now, end=deadline)
            if cumulative_required > capacity:
                shortfall = round(cumulative_required - capacity, 2)
                conflicts.append(
                    f"{task.title}: cumulative workload exceeds available study "
                    f"capacity before its deadline by {shortfall}h"
                )
        return conflicts

    def validate_plan_capacity(
        self,
        user_id: str,
        *,
        sessions: list[StudySession | dict[str, Any]],
    ) -> dict[str, Any]:
        adapter = TypeAdapter(list[StudySession])
        validated = adapter.validate_python(sessions)
        availability = self.database.list_availability(user_id)
        tasks = {task.id: task for task in self.database.list_tasks(user_id)}
        courses = {course.id for course in self.database.list_courses(user_id)}

        issues: list[str] = []
        by_date: dict[date, list[StudySession]] = defaultdict(list)
        planned_by_task: dict[str, float] = defaultdict(float)

        for session in validated:
            by_date[session.date].append(session)
            planned_by_task[session.task_id] += session.planned_hours

            task = tasks.get(session.task_id)
            if task is None:
                issues.append(f"session references unknown task {session.task_id}")
            elif task.course_id != session.course_id:
                issues.append(f"session course does not match task {session.task_id}")
            if session.course_id not in courses:
                issues.append(f"session references unknown course {session.course_id}")

            matching_windows = [
                window
                for window in availability
                if window.date == session.date
                and _minutes(window.start_time) <= _minutes(session.start_time)
                and _minutes(window.end_time) >= _minutes(session.end_time)
            ]
            if not matching_windows:
                issues.append(
                    f"session for task {session.task_id} on {session.date.isoformat()} "
                    "falls outside declared availability"
                )

        for day, day_sessions in by_date.items():
            ordered = sorted(day_sessions, key=lambda item: _minutes(item.start_time))
            for first, second in zip(ordered, ordered[1:]):
                if _minutes(second.start_time) < _minutes(first.end_time):
                    issues.append(
                        f"overlapping study sessions on {day.isoformat()}: "
                        f"{first.task_id} and {second.task_id}"
                    )

        for task_id, planned in planned_by_task.items():
            task = tasks.get(task_id)
            if task and planned > task.estimated_hours + 0.02:
                issues.append(
                    f"task {task_id} is over-allocated by "
                    f"{round(planned - task.estimated_hours, 2)}h"
                )

        return {
            "valid": not issues,
            "issue_count": len(issues),
            "issues": issues,
            "planned_hours": round(sum(s.planned_hours for s in validated), 2),
        }

    def save_study_plan(self, plan: StudyPlan | dict[str, Any]) -> dict[str, Any]:
        if isinstance(plan, dict):
            plan = StudyPlan.model_validate(plan)
        self.database.save_plan(plan)
        return plan.model_dump(mode="json")

    def load_study_plan(
        self, *, thread_id: str, user_id: str
    ) -> dict[str, Any] | None:
        plan = self.database.load_plan(thread_id, user_id=user_id)
        return plan.model_dump(mode="json") if plan else None
