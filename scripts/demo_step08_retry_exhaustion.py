"""Capture the real LangGraph safe-failure termination path.

PROJECT_SPEC.md Section 9 requires: "Re-planning is capped by a configured
maximum retry count. If the retry limit is reached, the graph returns a safe
failure status with actionable feedback." This exercises exactly that path on
the real installed LangGraph runtime using a genuinely infeasible workload
(100 required hours against 1 available hour) that no re-planning strategy can
repair, so the Reviewer keeps rejecting until ``route_review`` routes to the
``failed`` terminal node instead of looping forever.
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

from app.graph.workflow import build_workflow
from app.persistence import Database
from app.tools import StudyTools

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
APP_DB = Path("data/step08_retry_exhaustion.sqlite")
EVIDENCE = Path("evidence/step08_retry_exhaustion.txt")
MAX_REPLANS = 3


def emit(lines: list[str]) -> None:
    text = "\n".join(lines) + "\n"
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(text, encoding="utf-8")
    print(text, end="")


def main() -> None:
    APP_DB.unlink(missing_ok=True)
    db = Database(APP_DB)
    db.initialize()
    tools = StudyTools(db, clock=lambda: NOW)

    user_id = "step08-exhaustion-student"
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
    # Only one hour of availability exists in total: no re-planning strategy
    # can ever close a 99-hour capacity gap, so every reviewer pass rejects.
    tools.set_availability(user_id, study_date="2026-08-13", start_time="18:00", end_time="19:00")

    graph = build_workflow(tools, max_replans=MAX_REPLANS, clock=lambda: NOW)
    thread_id = "step08-retry-exhaustion"
    config = {"configurable": {"thread_id": thread_id}}
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

    result = graph.invoke(initial, config=config)
    trace = list(result.get("graph_trace", []))
    planning_visits = trace.count("planning")
    reviewer_visits = trace.count("reviewer")
    retry_count = int(result.get("retry_count", 0))
    status = str(result.get("workflow_status", ""))
    reached_failed_node = trace and trace[-1] == "failed"

    success = (
        status == "failed_after_replans"
        and reached_failed_node
        and retry_count == MAX_REPLANS + 1
        and planning_visits == MAX_REPLANS + 1
        and reviewer_visits == MAX_REPLANS + 1
        and bool(result.get("errors"))
    )

    lines = [
        "=== STEP 8 RETRY-EXHAUSTION SAFE-FAILURE EVIDENCE ===",
        f"thread_id={thread_id}",
        f"max_replans={MAX_REPLANS}",
        f"final_retry_count={retry_count}",
        f"planning_node_visits={planning_visits}",
        f"reviewer_node_visits={reviewer_visits}",
        "graph_trace=" + repr(trace),
        f"final_workflow_status={status}",
        f"terminated_via_failed_node={reached_failed_node}",
        "errors=" + repr(list(result.get("errors", []))),
        f"RETRY_EXHAUSTION_SAFE_FAILURE_SUCCESS={str(success).lower()}",
    ]
    emit(lines)
    if not success:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
