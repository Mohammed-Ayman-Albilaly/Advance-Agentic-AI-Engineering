"""Capture real LangGraph branch/loop + durable HITL restart/resume evidence.

This uses the deterministic coordinator so the graph/persistence proof does not
require an external LLM. It intentionally creates a first plan that the Reviewer
rejects; the graph loops to Planning, repairs it, then pauses at interrupt().
The SQLite checkpointer is closed/reopened before Command(resume=...).
"""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if importlib.util.find_spec("langgraph") is None:
    raise SystemExit("LangGraph is not installed. Run: python -m pip install -r requirements.txt")

from langgraph.types import Command

from app.graph.workflow import build_workflow
from app.persistence import Database, SqliteCheckpointResource
from app.tools import StudyTools

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
APP_DB = Path("data/step08_full_graph.sqlite")
CHECKPOINT_DB = Path("data/step08_full_graph_checkpoints.sqlite")
EVIDENCE = Path("evidence/step08_full_graph_hitl.txt")


def emit(lines: list[str]) -> None:
    text = "\n".join(lines) + "\n"
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(text, encoding="utf-8")
    print(text, end="")


def seed(tools: StudyTools) -> tuple[str, str]:
    user_id = "step08-graph-student"
    course = tools.add_course(user_id, code="CEN 351", name="Signals and Systems", credit_hours=3)
    early = tools.add_task(
        user_id,
        title="Near low-priority assignment",
        course_id=course["id"],
        deadline="2026-08-13T20:00:00+00:00",
        estimated_hours=2,
        difficulty=1,
        user_priority="low",
    )
    tools.add_task(
        user_id,
        title="Later critical exam",
        course_id=course["id"],
        deadline="2026-08-14T20:00:00+00:00",
        estimated_hours=2,
        difficulty=5,
        user_priority="critical",
    )
    tools.set_availability(user_id, study_date="2026-08-13", start_time="18:00", end_time="20:00")
    tools.set_availability(user_id, study_date="2026-08-14", start_time="18:00", end_time="20:00")
    return user_id, early["id"]


def interrupt_present(result: dict) -> bool:
    return bool(result.get("__interrupt__"))


def main() -> None:
    for path in (APP_DB, CHECKPOINT_DB):
        path.unlink(missing_ok=True)

    db = Database(APP_DB)
    db.initialize()
    tools = StudyTools(db, clock=lambda: NOW)
    user_id, early_task_id = seed(tools)
    thread_id = "step08-real-graph-hitl"
    config = {"configurable": {"thread_id": thread_id}}
    initial = {
        "thread_id": thread_id,
        "user_id": user_id,
        "user_request": "Create a realistic plan and repair it if review finds a deadline problem.",
        "retry_count": 0,
        "tool_events": [],
        "agent_messages": [],
        "graph_trace": [],
        "errors": [],
    }

    with SqliteCheckpointResource(CHECKPOINT_DB) as checkpoints:
        graph = build_workflow(
            tools,
            checkpointer=checkpoints.saver,
            clock=lambda: NOW,
        )
        paused = graph.invoke(initial, config=config)
        trace_before = list(paused.get("graph_trace", []))
        retry_count = int(paused.get("retry_count", 0))
        strategy = str(paused.get("planning_strategy", ""))
        sessions = list((paused.get("proposed_plan") or {}).get("sessions", []))
        first_after_replan = sessions[0]["task_id"] if sessions else ""
        paused_ok = interrupt_present(paused)
        replan_ok = (
            retry_count >= 1
            and strategy == "deadline_first_replan"
            and first_after_replan == early_task_id
            and trace_before.count("planning") >= 2
            and trace_before.count("reviewer") >= 2
        )

    # Closing the first context simulates process termination.
    restarted_db = Database(APP_DB)
    restarted_db.initialize()
    restarted_tools = StudyTools(restarted_db, clock=lambda: NOW)
    with SqliteCheckpointResource(CHECKPOINT_DB) as checkpoints:
        restarted_graph = build_workflow(
            restarted_tools,
            checkpointer=checkpoints.saver,
            clock=lambda: NOW,
        )
        completed = restarted_graph.invoke(
            Command(resume={"decision": "approved"}),
            config=config,
        )
        stored = restarted_tools.load_study_plan(thread_id=thread_id, user_id=user_id)

    resume_ok = (
        paused_ok
        and completed.get("workflow_status") == "completed"
        and completed.get("approval_status") == "approved"
        and stored is not None
    )

    lines = [
        "=== STEP 8 REAL LANGGRAPH + DURABLE HITL EVIDENCE ===",
        f"thread_id={thread_id}",
        "checkpoint_backend=SqliteSaver",
        f"paused_at_interrupt={paused_ok}",
        f"retry_count_before_approval={retry_count}",
        f"planning_strategy_after_replan={strategy}",
        "graph_trace_before_approval=" + repr(trace_before),
        f"planning_node_visits={trace_before.count('planning')}",
        f"reviewer_node_visits={trace_before.count('reviewer')}",
        f"REPLAN_LOOP_SUCCESS={str(replan_ok).lower()}",
        "checkpoint_connection_closed=true",
        "graph_rebuilt_after_restart=true",
        f"resume_workflow_status={completed.get('workflow_status')}",
        f"approval_status={completed.get('approval_status')}",
        f"persisted_plan_after_restart={stored is not None}",
        f"HITL_RESTART_RESUME_SUCCESS={str(resume_ok).lower()}",
    ]
    emit(lines)
    if not (replan_ok and resume_ok):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
