"""End-to-end durable HITL demo for a normal environment with LangGraph installed.

Run after: pip install -r requirements.txt
This script intentionally closes and reopens the SQLite checkpointer between the
interrupt and the approval resume to prove restart-safe persistence.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from langgraph.types import Command

from app.graph.workflow import build_workflow
from app.persistence import Database, SqliteCheckpointResource
from app.tools import StudyTools


def main() -> None:
    app_db = Path("data/step05_demo_app.sqlite")
    checkpoint_db = Path("data/step05_demo_checkpoints.sqlite")
    for path in (app_db, checkpoint_db):
        path.unlink(missing_ok=True)

    db = Database(app_db)
    db.initialize()
    tools = StudyTools(db)
    user_id = "step05-demo-student"
    thread_id = "step05-durable-hitl"

    course = tools.add_course(user_id, code="CEN 351", name="Signals and Systems", credit_hours=3)
    now = datetime.now(timezone.utc)
    study_day = (now + timedelta(days=1)).date()
    tools.add_task(
        user_id,
        title="Signals assignment",
        course_id=course["id"],
        deadline=now + timedelta(days=2),
        estimated_hours=2.0,
        difficulty=3,
        user_priority="high",
    )
    tools.set_availability(
        user_id,
        study_date=study_day,
        start_time=time(18, 0),
        end_time=time(21, 0),
    )

    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "thread_id": thread_id,
        "user_id": user_id,
        "user_request": "Create a study plan for my current assignments.",
        "retry_count": 0,
        "tool_events": [],
        "agent_messages": [],
        "graph_trace": [],
        "errors": [],
    }

    # First process: run until interrupt, then close the checkpoint connection.
    with SqliteCheckpointResource(checkpoint_db) as checkpoints:
        graph = build_workflow(tools, checkpointer=checkpoints.saver)
        paused = graph.invoke(initial_state, config=config)
        print("PAUSED")
        print(f"workflow_status={paused.get('workflow_status')}")
        print(f"interrupt={paused.get('__interrupt__')}")

    print("CHECKPOINTER CLOSED — SIMULATED APPLICATION RESTART")

    # Second process: rebuild the graph from the same persistent checkpoint DB.
    restarted_db = Database(app_db)
    restarted_db.initialize()
    restarted_tools = StudyTools(restarted_db)
    with SqliteCheckpointResource(checkpoint_db) as checkpoints:
        restarted_graph = build_workflow(restarted_tools, checkpointer=checkpoints.saver)
        completed = restarted_graph.invoke(
            Command(resume={"decision": "approved"}),
            config=config,
        )
        print("RESUMED")
        print(f"workflow_status={completed.get('workflow_status')}")
        print(f"approval_status={completed.get('approval_status')}")
        print(f"graph_trace={completed.get('graph_trace')}")
        stored = restarted_tools.load_study_plan(thread_id=thread_id, user_id=user_id)
        print(f"persisted_plan={stored is not None}")
        print(f"persisted_plan_status={stored.get('status') if stored else None}")


if __name__ == "__main__":
    main()
