"""LangGraph workflow definition for UniFlow AI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.agents import CoordinatorAgent, PlanningAgent, ReviewerAgent, TaskAnalysisAgent
from app.agents.base import tool_call
from app.graph.hitl import apply_approval_decision, approval_request_payload
from app.graph.state import StudyState
from app.guardrails import InputGuardrail, OutputGuardrail
from app.observability import get_observability
from app.tools import StudyTools


WORKFLOW_NODES = (
    "input_guardrail",
    "blocked",
    "coordinator",
    "task_analysis",
    "planning",
    "reviewer",
    "human_approval",
    "persist_final",
    "output_guardrail",
    "failed",
)


@dataclass(frozen=True)
class WorkflowSpec:
    nodes: tuple[str, ...]
    static_edges: tuple[tuple[str, str], ...]
    input_routes: dict[str, str]
    reviewer_routes: dict[str, str]
    approval_routes: dict[str, str]
    loops: tuple[tuple[str, str], ...]


def workflow_spec() -> WorkflowSpec:
    """Machine-testable representation of the graph's security/HITL topology."""

    return WorkflowSpec(
        nodes=WORKFLOW_NODES,
        static_edges=(
            ("START", "input_guardrail"),
            ("coordinator", "task_analysis"),
            ("task_analysis", "planning"),
            ("planning", "reviewer"),
            ("persist_final", "output_guardrail"),
            ("output_guardrail", "END"),
            ("blocked", "END"),
            ("failed", "END"),
        ),
        input_routes={"allowed": "coordinator", "blocked": "blocked"},
        reviewer_routes={
            "approved": "human_approval",
            "replan": "planning",
            "failed": "failed",
        },
        approval_routes={
            "approved": "persist_final",
            "replan": "planning",
            "failed": "failed",
        },
        loops=(("reviewer", "planning"), ("human_approval", "planning")),
    )


def build_workflow(
    tools: StudyTools,
    *,
    max_replans: int = 3,
    checkpointer: Any | None = None,
    clock: Callable | None = None,
    llm_coordinator: Any | None = None,
):
    """Build and compile the genuine LangGraph ``StateGraph``.

    A durable checkpointer is required at runtime for true interrupt/resume. The
    graph can still be compiled without one for topology/unit checks, but calling
    the HITL path without checkpointing is intentionally unsupported by LangGraph.
    """

    from langgraph.graph import END, START, StateGraph
    from langgraph.types import interrupt

    coordinator = CoordinatorAgent(tools, llm_coordinator=llm_coordinator)
    analyzer = TaskAnalysisAgent(tools)
    planner = PlanningAgent(**({"clock": clock} if clock is not None else {}))
    reviewer = ReviewerAgent(tools)
    input_guard = InputGuardrail()
    output_guard = OutputGuardrail()
    observer = get_observability()

    def input_guardrail_node(state: StudyState) -> dict[str, Any]:
        decision = input_guard.inspect(state.get("user_request", ""))
        if not decision.allowed:
            observer.record_guardrail_block("input", state.get("thread_id", ""), decision.reason)
        return {
            "guardrail_status": decision.status,
            "guardrail_reason": decision.reason,
            "workflow_status": "input_allowed" if decision.allowed else "blocked_by_input_guardrail",
            "graph_trace": ["input_guardrail"],
        }

    def route_input(state: StudyState) -> str:
        return "allowed" if state.get("guardrail_status") == "passed" else "blocked"

    def blocked_node(state: StudyState) -> dict[str, Any]:
        observer.record_workflow_outcome("blocked", state.get("thread_id", ""))
        return {
            "workflow_status": "blocked",
            "errors": [state.get("guardrail_reason", "Request blocked by input guardrail.")],
            "graph_trace": ["blocked"],
        }

    def coordinator_node(state: StudyState) -> dict[str, Any]:
        return {**coordinator.run(state), "graph_trace": ["coordinator"]}

    def analysis_node(state: StudyState) -> dict[str, Any]:
        return {**analyzer.run(state), "graph_trace": ["task_analysis"]}

    def planning_node(state: StudyState) -> dict[str, Any]:
        return {**planner.run(state), "graph_trace": ["planning"]}

    def reviewer_node(state: StudyState) -> dict[str, Any]:
        return {**reviewer.run(state), "graph_trace": ["reviewer"]}

    def route_review(state: StudyState) -> str:
        if state.get("review_status") == "approved":
            return "approved"
        retry_count = int(state.get("retry_count", 0))
        if retry_count <= max_replans:
            observer.record_replan("reviewer", state.get("thread_id", ""))
            return "replan"
        return "failed"

    def human_approval_node(state: StudyState) -> dict[str, Any]:
        # Keep side effects after interrupt: LangGraph restarts this node on resume.
        raw_decision = interrupt(approval_request_payload(state))
        update = apply_approval_decision(state, raw_decision)
        observer.record_approval(str(update.get("approval_status", "unknown")), state.get("thread_id", ""))
        if update.get("approval_status") == "rejected":
            observer.record_replan("human_approval", state.get("thread_id", ""))
        return {**update, "graph_trace": ["human_approval"]}

    def route_approval(state: StudyState) -> str:
        if state.get("approval_status") == "approved":
            return "approved"
        if state.get("approval_status") == "rejected":
            if int(state.get("retry_count", 0)) <= max_replans:
                return "replan"
            return "failed"
        return "failed"

    def persist_final_node(state: StudyState) -> dict[str, Any]:
        final_plan = state.get("final_plan") or {}
        saved, event = tool_call(
            state,
            node="persist_final",
            agent="CoordinatorAgent",
            tool_name="save_study_plan",
            operation=lambda: tools.save_study_plan(final_plan),
        )
        return {
            "final_plan": saved,
            "workflow_status": "approved_plan_persisted",
            "tool_events": [event],
            "graph_trace": ["persist_final"],
        }

    def output_guardrail_node(state: StudyState) -> dict[str, Any]:
        result = output_guard.protect_plan(dict(state.get("final_plan") or {}))
        if not result.allowed:
            observer.record_guardrail_block("output", state.get("thread_id", ""), result.reason)
            observer.record_workflow_outcome("blocked_by_output_guardrail", state.get("thread_id", ""))
            return {
                "guardrail_status": "blocked",
                "guardrail_reason": result.reason,
                "workflow_status": "blocked_by_output_guardrail",
                "errors": [result.reason],
                "graph_trace": ["output_guardrail"],
            }
        observer.record_workflow_outcome("completed", state.get("thread_id", ""))
        return {
            "final_plan": result.sanitized_output or {},
            "guardrail_status": "passed",
            "guardrail_reason": result.reason,
            "workflow_status": "completed",
            "graph_trace": ["output_guardrail"],
        }

    def failed_node(state: StudyState) -> dict[str, Any]:
        feedback = state.get("reviewer_feedback", [])
        observer.record_workflow_outcome("failed_after_replans", state.get("thread_id", ""))
        return {
            "workflow_status": "failed_after_replans",
            "errors": [
                "maximum re-planning/approval attempts exhausted"
                + (f": {'; '.join(feedback)}" if feedback else "")
            ],
            "graph_trace": ["failed"],
        }

    builder = StateGraph(StudyState)
    builder.add_node("input_guardrail", observer.observed_node("input_guardrail", input_guardrail_node))
    builder.add_node("blocked", observer.observed_node("blocked", blocked_node))
    builder.add_node("coordinator", observer.observed_node("coordinator", coordinator_node))
    builder.add_node("task_analysis", observer.observed_node("task_analysis", analysis_node))
    builder.add_node("planning", observer.observed_node("planning", planning_node))
    builder.add_node("reviewer", observer.observed_node("reviewer", reviewer_node))
    builder.add_node("human_approval", observer.observed_node("human_approval", human_approval_node))
    builder.add_node("persist_final", observer.observed_node("persist_final", persist_final_node))
    builder.add_node("output_guardrail", observer.observed_node("output_guardrail", output_guardrail_node))
    builder.add_node("failed", observer.observed_node("failed", failed_node))

    builder.add_edge(START, "input_guardrail")
    builder.add_conditional_edges(
        "input_guardrail", route_input, {"allowed": "coordinator", "blocked": "blocked"}
    )
    builder.add_edge("coordinator", "task_analysis")
    builder.add_edge("task_analysis", "planning")
    builder.add_edge("planning", "reviewer")
    builder.add_conditional_edges(
        "reviewer",
        route_review,
        {"approved": "human_approval", "replan": "planning", "failed": "failed"},
    )
    builder.add_conditional_edges(
        "human_approval",
        route_approval,
        {"approved": "persist_final", "replan": "planning", "failed": "failed"},
    )
    builder.add_edge("persist_final", "output_guardrail")
    builder.add_edge("output_guardrail", END)
    builder.add_edge("blocked", END)
    builder.add_edge("failed", END)

    return builder.compile(checkpointer=checkpointer)
