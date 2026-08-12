"""Reviewer agent: independent feasibility and completeness review."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.agents.base import message, tool_call
from app.graph.state import StudyState
from app.tools import StudyTools


def _aware(value: str | datetime) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class ReviewerAgent:
    name = "ReviewerAgent"
    node = "reviewer"

    def __init__(self, tools: StudyTools) -> None:
        self.tools = tools

    def run(self, state: StudyState) -> dict[str, Any]:
        user_id = state["user_id"]
        plan = state.get("proposed_plan", {})
        sessions = list(plan.get("sessions", []))
        events: list[dict[str, Any]] = []
        feedback: list[str] = []

        validation, event = tool_call(
            state,
            node=self.node,
            agent=self.name,
            tool_name="validate_plan_capacity",
            operation=lambda: self.tools.validate_plan_capacity(user_id, sessions=sessions),
        )
        events.append(event)
        feedback.extend(validation["issues"])

        deadline_conflicts, event = tool_call(
            state,
            node=self.node,
            agent=self.name,
            tool_name="check_deadline_conflicts",
            operation=lambda: self.tools.check_deadline_conflicts(user_id),
        )
        events.append(event)
        feedback.extend(deadline_conflicts)

        planned_by_task: dict[str, float] = defaultdict(float)
        sessions_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for session in sessions:
            planned_by_task[session["task_id"]] += float(session["planned_hours"])
            sessions_by_task[session["task_id"]].append(session)

        for task in state.get("tasks", []):
            planned = round(planned_by_task.get(task["id"], 0.0), 2)
            required = float(task["estimated_hours"])
            if planned + 0.02 < required:
                feedback.append(
                    f"task {task['id']} is under-planned by {round(required - planned, 2)}h"
                )
            deadline = _aware(task["deadline"])
            for session in sessions_by_task.get(task["id"], []):
                end = datetime.combine(
                    datetime.fromisoformat(session["date"]).date(),
                    datetime.fromisoformat(f"2000-01-01T{session['end_time']}").time(),
                    tzinfo=deadline.tzinfo or timezone.utc,
                )
                if end > deadline:
                    feedback.append(f"task {task['id']} has a session after its deadline")
                    break

        # Preserve order while removing duplicates for stable evidence/tests.
        feedback = list(dict.fromkeys(feedback))
        approved = not feedback
        review_status = "approved" if approved else "replan_required"
        next_retry_count = int(state.get("retry_count", 0)) + (0 if approved else 1)

        recipient = "HumanApproval" if approved else "PlanningAgent"
        handoff = message(
            sender=self.name,
            recipient=recipient,
            message_type="review_result",
            payload={
                "status": review_status,
                "feedback": feedback,
                "next_retry_count": next_retry_count,
            },
        )
        return {
            "review_status": review_status,
            "reviewer_feedback": feedback,
            "conflicts": feedback,
            "retry_count": next_retry_count,
            "workflow_status": "review_approved" if approved else "replan_required",
            "tool_events": events,
            "agent_messages": [handoff],
        }
