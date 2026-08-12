"""Captured Step 4 demo of specialized agents and reviewer-driven re-planning.

This script exercises the exact agent classes used by the LangGraph nodes. It
runs without importing LangGraph so evidence can still be captured in restricted
sandboxes where dependency installation is unavailable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agents import CoordinatorAgent, PlanningAgent, ReviewerAgent, TaskAnalysisAgent
from app.persistence import Database
from app.tools import StudyTools


NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def main() -> None:
    with TemporaryDirectory() as directory:
        db = Database(Path(directory) / "demo.sqlite")
        db.initialize()
        tools = StudyTools(db, clock=lambda: NOW)

        course = tools.add_course(
            "demo-student", code="CEN 351", name="Signals and Systems", credit_hours=3
        )
        early = tools.add_task(
            "demo-student",
            title="Near low-priority assignment",
            course_id=course["id"],
            deadline="2026-08-13T20:00:00+00:00",
            estimated_hours=2,
            difficulty=1,
            user_priority="low",
        )
        late = tools.add_task(
            "demo-student",
            title="Later critical exam",
            course_id=course["id"],
            deadline="2026-08-14T20:00:00+00:00",
            estimated_hours=2,
            difficulty=5,
            user_priority="critical",
        )
        tools.set_availability(
            "demo-student", study_date="2026-08-13", start_time="18:00", end_time="20:00"
        )
        tools.set_availability(
            "demo-student", study_date="2026-08-14", start_time="18:00", end_time="20:00"
        )

        coordinator = CoordinatorAgent(tools)
        analyzer = TaskAnalysisAgent(tools)
        planner = PlanningAgent(clock=lambda: NOW)
        reviewer = ReviewerAgent(tools)

        state = {
            "thread_id": "step04-demo",
            "user_id": "demo-student",
            "user_request": "Create my study plan",
            "retry_count": 0,
        }

        print("=== STEP 4 MULTI-AGENT REPLAN DEMO ===")
        print("Coordinator -> TaskAnalysis -> Planning -> Reviewer")
        print()

        coordinated = coordinator.run(state)
        state.update(coordinated)
        print(f"Coordinator intent: {state['intent']}")
        print(f"Coordinator real tool calls: {[e['tool_name'] for e in coordinated['tool_events']]}")

        analyzed = analyzer.run(state)
        state.update(analyzed)
        score_by_id = {item["task_id"]: item["priority_score"] for item in state["analyzed_tasks"]}
        print(f"Early task priority score: {score_by_id[early['id']]}")
        print(f"Later critical task priority score: {score_by_id[late['id']]}")
        print()

        first_plan = planner.run(state)
        state.update(first_plan)
        first_task = state["proposed_plan"]["sessions"][0]["task_id"]
        print(f"Attempt 0 strategy: {state['planning_strategy']}")
        print(f"First scheduled task is later critical task: {first_task == late['id']}")

        first_review = reviewer.run(state)
        state.update(first_review)
        print(f"Reviewer result: {state['review_status']}")
        print(f"Retry count: {state['retry_count']}")
        print("Reviewer feedback:")
        for item in state["reviewer_feedback"]:
            print(f"- {item}")
        print()

        second_plan = planner.run(state)
        state.update(second_plan)
        first_task_after_replan = state["proposed_plan"]["sessions"][0]["task_id"]
        print(f"Attempt 1 strategy: {state['planning_strategy']}")
        print(f"First scheduled task is now near-deadline task: {first_task_after_replan == early['id']}")

        second_review = reviewer.run(state)
        state.update(second_review)
        print(f"Reviewer result after replan: {state['review_status']}")
        print(f"Reviewer feedback after replan: {state['reviewer_feedback']}")
        print()
        print("RESULT: reviewer feedback changed planning strategy and repaired the plan.")


if __name__ == "__main__":
    main()
