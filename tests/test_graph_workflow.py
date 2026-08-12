import importlib.util

import pytest

from app.graph.workflow import WORKFLOW_NODES, build_workflow, workflow_spec
from app.persistence import Database
from app.tools import StudyTools


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
