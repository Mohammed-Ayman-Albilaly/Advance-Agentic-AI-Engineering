"""Task Analysis agent: urgency, effort, and workload reasoning."""

from __future__ import annotations

from typing import Any

from app.agents.base import message, tool_call
from app.graph.state import StudyState
from app.tools import StudyTools


class TaskAnalysisAgent:
    name = "TaskAnalysisAgent"
    node = "task_analysis"

    def __init__(self, tools: StudyTools) -> None:
        self.tools = tools

    def run(self, state: StudyState) -> dict[str, Any]:
        analyzed: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        for task in state.get("tasks", []):
            result, event = tool_call(
                state,
                node=self.node,
                agent=self.name,
                tool_name="calculate_task_priority",
                operation=lambda task=task: self.tools.calculate_task_priority(task),
            )
            analyzed.append(result)
            events.append(event)

        analyzed.sort(key=lambda item: (-float(item["priority_score"]), item["task_id"]))
        handoff = message(
            sender=self.name,
            recipient="PlanningAgent",
            message_type="planning_context",
            payload={
                "analyzed_task_count": len(analyzed),
                "highest_priority_score": analyzed[0]["priority_score"] if analyzed else None,
            },
        )
        return {
            "analyzed_tasks": analyzed,
            "workflow_status": "tasks_analyzed",
            "tool_events": events,
            "agent_messages": [handoff],
        }
