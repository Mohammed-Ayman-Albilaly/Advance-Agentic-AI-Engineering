"""Shared LangGraph state contract for UniFlow AI."""

from __future__ import annotations

import operator
from typing import Annotated, Any
from typing_extensions import TypedDict


class StudyState(TypedDict, total=False):
    # Identity / routing
    thread_id: str
    user_id: str
    user_request: str
    intent: str
    coordination_mode: str
    llm_summary: str
    llm_provider: str
    llm_model: str
    llm_calls: int

    # Input domain data (JSON-serializable dictionaries)
    courses: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    availability: list[dict[str, Any]]

    # Agent-produced data
    analyzed_tasks: list[dict[str, Any]]
    planning_strategy: str
    proposed_plan: dict[str, Any]
    unscheduled_hours: dict[str, float]
    conflicts: list[str]
    review_status: str
    reviewer_feedback: list[str]

    # Loop / HITL / terminal state
    retry_count: int
    approval_status: str
    approval_feedback: str
    final_plan: dict[str, Any]
    workflow_status: str

    # Guardrail state
    guardrail_status: str
    guardrail_reason: str

    # Append-only structured evidence channels.
    tool_events: Annotated[list[dict[str, Any]], operator.add]
    agent_messages: Annotated[list[dict[str, Any]], operator.add]
    graph_trace: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
