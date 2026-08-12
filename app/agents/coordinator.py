"""Coordinator agent: central routing and context assembly."""

from __future__ import annotations

from typing import Any

from app.agents.base import message, tool_call
from app.graph.state import StudyState
from app.tools import StudyTools


class CoordinatorAgent:
    """Central coordinator in the project's centralized coordination strategy.

    When an LLM coordinator is supplied, persisted context is acquired through a
    genuine provider function-calling loop. Without one, the deterministic path
    remains available for offline development/tests and is explicitly marked as
    such in state rather than being misrepresented as a live LLM run.
    """

    name = "CoordinatorAgent"
    node = "coordinator"

    def __init__(self, tools: StudyTools, *, llm_coordinator: Any | None = None) -> None:
        self.tools = tools
        self.llm_coordinator = llm_coordinator

    @staticmethod
    def _infer_intent(request: str) -> str:
        normalized = request.casefold()
        planning_terms = (
            "plan",
            "schedule",
            "study",
            "organize",
            "organise",
            "جدول",
            "خطة",
            "دراسة",
            "رتب",
        )
        return "create_study_plan" if any(term in normalized for term in planning_terms) else "create_study_plan"

    def _deterministic_context(self, state: StudyState) -> tuple[list, list, list, list[dict[str, Any]]]:
        user_id = state["user_id"]
        events: list[dict[str, Any]] = []
        courses, event = tool_call(
            state,
            node=self.node,
            agent=self.name,
            tool_name="get_courses",
            operation=lambda: self.tools.get_courses(user_id),
        )
        events.append(event)
        tasks, event = tool_call(
            state,
            node=self.node,
            agent=self.name,
            tool_name="get_tasks",
            operation=lambda: self.tools.get_tasks(user_id, include_done=False),
        )
        events.append(event)
        availability, event = tool_call(
            state,
            node=self.node,
            agent=self.name,
            tool_name="get_availability_windows",
            operation=lambda: self.tools.get_availability_windows(user_id),
        )
        events.append(event)
        return courses, tasks, availability, events

    def run(self, state: StudyState) -> dict[str, Any]:
        llm_summary = ""
        llm_provider = "not_configured"
        llm_model = ""
        llm_calls = 0
        mode = "deterministic_offline"

        if self.llm_coordinator is not None:
            result = self.llm_coordinator.run(state)
            courses = list(result.tool_results.get("get_courses", []))
            tasks = list(result.tool_results.get("get_tasks", []))
            availability = list(result.tool_results.get("get_availability_windows", []))
            events = list(result.tool_events)
            llm_summary = result.summary
            llm_provider = result.provider
            llm_model = result.model
            llm_calls = result.llm_calls
            mode = "llm_function_calling"
        else:
            courses, tasks, availability, events = self._deterministic_context(state)

        intent = self._infer_intent(state.get("user_request", ""))
        handoff = message(
            sender=self.name,
            recipient="TaskAnalysisAgent",
            message_type="analysis_request",
            payload={
                "intent": intent,
                "task_count": len(tasks),
                "course_count": len(courses),
                "availability_window_count": len(availability),
                "coordination_mode": mode,
                "llm_summary": llm_summary,
            },
        )
        return {
            "intent": intent,
            "courses": courses,
            "tasks": tasks,
            "availability": availability,
            "retry_count": int(state.get("retry_count", 0)),
            "workflow_status": "coordinated",
            "tool_events": events,
            "agent_messages": [handoff],
            "coordination_mode": mode,
            "llm_summary": llm_summary,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_calls": llm_calls,
        }
