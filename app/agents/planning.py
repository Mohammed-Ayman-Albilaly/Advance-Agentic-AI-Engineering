"""Planning agent implementing the project's Plan-and-Execute planning stage."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timezone
from typing import Any, Callable

from app.agents.base import message, utc_now
from app.graph.state import StudyState


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _as_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return _ensure_aware(value)
    return _ensure_aware(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _as_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def _as_time(value: str | time) -> time:
    return value if isinstance(value, time) else time.fromisoformat(value)


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _time_from_minutes(value: int) -> time:
    hours, minutes = divmod(value, 60)
    return time(hour=hours, minute=minutes)


class PlanningAgent:
    """Build a concrete schedule and adapt strategy after reviewer feedback.

    First pass is priority-led. If the reviewer rejects that plan, the next pass
    switches to deadline-first planning. This makes reviewer feedback capable of
    changing subsequent planning behavior rather than merely repeating a prompt.
    """

    name = "PlanningAgent"
    node = "planning"

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = utc_now,
        max_session_hours: float = 2.0,
    ) -> None:
        self.clock = clock
        self.max_session_minutes = max(30, int(round(max_session_hours * 60)))

    def _ordered_tasks(self, state: StudyState) -> tuple[list[dict[str, Any]], str]:
        analyzed = {item["task_id"]: item for item in state.get("analyzed_tasks", [])}
        tasks = list(state.get("tasks", []))
        retry_count = int(state.get("retry_count", 0))

        if retry_count == 0:
            strategy = "priority_first"
            tasks.sort(
                key=lambda task: (
                    -float(analyzed.get(task["id"], {}).get("priority_score", 0)),
                    _as_datetime(task["deadline"]),
                )
            )
        else:
            strategy = "deadline_first_replan"
            tasks.sort(
                key=lambda task: (
                    _as_datetime(task["deadline"]),
                    -float(analyzed.get(task["id"], {}).get("priority_score", 0)),
                )
            )
        return tasks, strategy

    def run(self, state: StudyState) -> dict[str, Any]:
        now = _ensure_aware(self.clock())
        tasks, strategy = self._ordered_tasks(state)

        slots: list[dict[str, Any]] = []
        for window in state.get("availability", []):
            day = _as_date(window["date"])
            start = _minutes(_as_time(window["start_time"]))
            end = _minutes(_as_time(window["end_time"]))
            if day < now.date():
                continue
            if day == now.date():
                start = max(start, now.hour * 60 + now.minute)
            if end > start:
                slots.append({"date": day, "cursor": start, "end": end})
        slots.sort(key=lambda slot: (slot["date"], slot["cursor"]))

        sessions: list[dict[str, Any]] = []
        unscheduled: dict[str, float] = {}
        for task in tasks:
            deadline = _as_datetime(task["deadline"])
            remaining_minutes = int(round(float(task["estimated_hours"]) * 60))

            for slot in slots:
                if remaining_minutes <= 0:
                    break
                if slot["cursor"] >= slot["end"]:
                    continue

                day = slot["date"]
                if day > deadline.date():
                    continue
                usable_end = int(slot["end"])
                if day == deadline.date():
                    usable_end = min(usable_end, deadline.hour * 60 + deadline.minute)
                if usable_end <= slot["cursor"]:
                    continue

                chunk = min(
                    remaining_minutes,
                    usable_end - int(slot["cursor"]),
                    self.max_session_minutes,
                )
                if chunk <= 0:
                    continue

                start_minute = int(slot["cursor"])
                end_minute = start_minute + chunk
                sessions.append(
                    {
                        "task_id": task["id"],
                        "course_id": task["course_id"],
                        "date": day.isoformat(),
                        "start_time": _time_from_minutes(start_minute).isoformat(timespec="minutes"),
                        "end_time": _time_from_minutes(end_minute).isoformat(timespec="minutes"),
                        "planned_hours": round(chunk / 60, 2),
                        "rationale": (
                            f"{strategy}: scheduled before {deadline.isoformat()} "
                            f"using current task priority and available capacity."
                        ),
                    }
                )
                slot["cursor"] = end_minute
                remaining_minutes -= chunk

            if remaining_minutes > 0:
                unscheduled[task["id"]] = round(remaining_minutes / 60, 2)

        total = round(sum(float(session["planned_hours"]) for session in sessions), 2)
        proposed_plan = {
            "thread_id": state["thread_id"],
            "user_id": state["user_id"],
            "status": "draft",
            "sessions": sessions,
            "summary": (
                f"Planning strategy={strategy}; sessions={len(sessions)}; "
                f"planned_hours={total}; unscheduled_tasks={len(unscheduled)}."
            ),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        handoff = message(
            sender=self.name,
            recipient="ReviewerAgent",
            message_type="plan_review_request",
            payload={
                "strategy": strategy,
                "session_count": len(sessions),
                "unscheduled_hours": unscheduled,
                "retry_count": int(state.get("retry_count", 0)),
            },
        )
        return {
            "planning_strategy": strategy,
            "proposed_plan": proposed_plan,
            "unscheduled_hours": unscheduled,
            "workflow_status": "plan_proposed",
            "agent_messages": [handoff],
        }
