import importlib.util
from datetime import datetime, timezone

import pytest

from app.graph.workflow import WORKFLOW_NODES, build_workflow, workflow_spec
from app.persistence import Database
from app.tools import StudyTools

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def test_workflow_spec_contains_security_hitl_branches_and_loops():
    spec = workflow_spec()
    assert set(WORKFLOW_NODES) == set(spec.nodes)
    assert ("START", "input_guardrail") in spec.static_edges
    assert spec.input_routes == {"allowed": "coordinator", "blocked": "blocked"}
    assert spec.reviewer_routes["approved"] == "human_approval"
    assert spec.reviewer_routes["replan"] == "planning"
    assert spec.reviewer_routes["failed"] == "failed"
    assert spec.approval_routes["approved"] == "persist_final"
    assert spec.approval_routes["replan"] == "planning"
    assert ("reviewer", "planning") in spec.loops
    assert ("human_approval", "planning") in spec.loops
    assert ("persist_final", "output_guardrail") in spec.static_edges


@pytest.mark.skipif(
    importlib.util.find_spec("langgraph") is None,
    reason="LangGraph dependency unavailable in this execution sandbox",
)
def test_real_langgraph_stategraph_compiles_when_dependency_is_available(tmp_path):
    db = Database(tmp_path / "graph.sqlite")
    db.initialize()
    graph = build_workflow(StudyTools(db))
    assert graph is not None
    assert hasattr(graph, "invoke")


@pytest.mark.skipif(
    importlib.util.find_spec("langgraph") is None,
    reason="LangGraph dependency unavailable in this execution sandbox",
)
def test_real_graph_terminates_via_failed_node_when_retries_exhausted(tmp_path):
    """PROJECT_SPEC.md Sec. 9: exhausted re-planning must reach a safe terminal
    failure instead of looping forever. A 100h task against 1h of availability
    is infeasible under every planning strategy, so the Reviewer always rejects.
    """

    max_replans = 3
    db = Database(tmp_path / "graph.sqlite")
    db.initialize()
    tools = StudyTools(db, clock=lambda: NOW)
    user_id = "exhaustion-student"
    course = tools.add_course(user_id, code="CEN 999", name="Impossible Workload", credit_hours=3)
    tools.add_task(
        user_id,
        title="Structurally infeasible task",
        course_id=course["id"],
        deadline="2026-08-14T20:00:00+00:00",
        estimated_hours=100,
        difficulty=5,
        user_priority="critical",
    )
    tools.set_availability(user_id, study_date="2026-08-13", start_time="18:00", end_time="19:00")

    graph = build_workflow(tools, max_replans=max_replans, clock=lambda: NOW)
    thread_id = "exhaustion-thread"
    initial = {
        "thread_id": thread_id,
        "user_id": user_id,
        "user_request": "Create a plan for a workload that cannot fit available time.",
        "retry_count": 0,
        "tool_events": [],
        "agent_messages": [],
        "graph_trace": [],
        "errors": [],
    }

    result = graph.invoke(initial, config={"configurable": {"thread_id": thread_id}})

    trace = list(result.get("graph_trace", []))
    assert trace[-1] == "failed"
    assert trace.count("planning") == max_replans + 1
    assert trace.count("reviewer") == max_replans + 1
    assert int(result.get("retry_count", 0)) == max_replans + 1
    assert result.get("workflow_status") == "failed_after_replans"
    assert result.get("errors")
