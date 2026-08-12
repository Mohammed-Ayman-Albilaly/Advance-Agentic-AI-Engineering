import sqlite3
from datetime import datetime, timezone

import pytest

from app.agents import CoordinatorAgent, PlanningAgent, ReviewerAgent, TaskAnalysisAgent
from app.agents.base import tool_call
from app.persistence import Database
from app.tools import StudyTools


NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def make_system(tmp_path):
    db = Database(tmp_path / "agents.sqlite")
    db.initialize()
    tools = StudyTools(db, clock=lambda: NOW)
    return tools


def seed_replan_scenario(tools: StudyTools):
    course = tools.add_course(
        "student-1", code="CEN 351", name="Signals and Systems", credit_hours=3
    )
    early = tools.add_task(
        "student-1",
        title="Near low-priority assignment",
        course_id=course["id"],
        deadline="2026-08-13T20:00:00+00:00",
        estimated_hours=2,
        difficulty=1,
        user_priority="low",
    )
    late = tools.add_task(
        "student-1",
        title="Later critical exam",
        course_id=course["id"],
        deadline="2026-08-14T20:00:00+00:00",
        estimated_hours=2,
        difficulty=5,
        user_priority="critical",
    )
    tools.set_availability(
        "student-1", study_date="2026-08-13", start_time="18:00", end_time="20:00"
    )
    tools.set_availability(
        "student-1", study_date="2026-08-14", start_time="18:00", end_time="20:00"
    )
    return early, late


def test_coordinator_loads_real_context_and_emits_structured_handoff(tmp_path):
    tools = make_system(tmp_path)
    seed_replan_scenario(tools)
    state = {
        "thread_id": "thread-1",
        "user_id": "student-1",
        "user_request": "Create my study plan",
        "retry_count": 0,
    }

    result = CoordinatorAgent(tools).run(state)

    assert result["intent"] == "create_study_plan"
    assert len(result["tasks"]) == 2
    assert len(result["availability"]) == 2
    assert [event["tool_name"] for event in result["tool_events"]] == [
        "get_courses",
        "get_tasks",
        "get_availability_windows",
    ]
    assert all(event["success"] for event in result["tool_events"])
    assert result["agent_messages"][0]["recipient"] == "TaskAnalysisAgent"


def test_task_analysis_agent_calls_priority_tool_for_every_task(tmp_path):
    tools = make_system(tmp_path)
    seed_replan_scenario(tools)
    initial = {
        "thread_id": "thread-1",
        "user_id": "student-1",
        "user_request": "Create my study plan",
        "retry_count": 0,
    }
    coordinated = CoordinatorAgent(tools).run(initial)
    state = {**initial, **coordinated}

    result = TaskAnalysisAgent(tools).run(state)

    assert len(result["analyzed_tasks"]) == 2
    assert len(result["tool_events"]) == 2
    assert all(event["tool_name"] == "calculate_task_priority" for event in result["tool_events"])
    assert result["analyzed_tasks"][0]["priority_score"] > result["analyzed_tasks"][1]["priority_score"]


def test_reviewer_feedback_changes_planning_strategy_and_fixes_plan(tmp_path):
    tools = make_system(tmp_path)
    early, late = seed_replan_scenario(tools)
    initial = {
        "thread_id": "thread-loop",
        "user_id": "student-1",
        "user_request": "Create my study plan",
        "retry_count": 0,
    }
    coordinator = CoordinatorAgent(tools)
    analyzer = TaskAnalysisAgent(tools)
    planner = PlanningAgent(clock=lambda: NOW)
    reviewer = ReviewerAgent(tools)

    state = {**initial, **coordinator.run(initial)}
    state = {**state, **analyzer.run(state)}

    first_plan = planner.run(state)
    state = {**state, **first_plan}
    assert first_plan["planning_strategy"] == "priority_first"
    assert first_plan["proposed_plan"]["sessions"][0]["task_id"] == late["id"]

    first_review = reviewer.run(state)
    assert first_review["review_status"] == "replan_required"
    assert first_review["retry_count"] == 1
    assert any(early["id"] in item and "under-planned" in item for item in first_review["reviewer_feedback"])

    state = {**state, **first_review}
    second_plan = planner.run(state)
    state = {**state, **second_plan}
    assert second_plan["planning_strategy"] == "deadline_first_replan"
    assert second_plan["proposed_plan"]["sessions"][0]["task_id"] == early["id"]

    second_review = reviewer.run(state)
    assert second_review["review_status"] == "approved"
    assert second_review["reviewer_feedback"] == []
    assert second_review["retry_count"] == 1


def test_planner_reports_unscheduled_hours_when_capacity_is_impossible(tmp_path):
    tools = make_system(tmp_path)
    course = tools.add_course("student-1", code="CSC 227", name="Operating Systems", credit_hours=3)
    task = tools.add_task(
        "student-1",
        title="Large project",
        course_id=course["id"],
        deadline="2026-08-13T20:00:00+00:00",
        estimated_hours=5,
        difficulty=5,
        user_priority="critical",
    )
    tools.set_availability(
        "student-1", study_date="2026-08-13", start_time="18:00", end_time="20:00"
    )
    initial = {"thread_id": "t", "user_id": "student-1", "user_request": "plan", "retry_count": 0}
    state = {**initial, **CoordinatorAgent(tools).run(initial)}
    state = {**state, **TaskAnalysisAgent(tools).run(state)}

    result = PlanningAgent(clock=lambda: NOW).run(state)
    assert result["unscheduled_hours"][task["id"]] == 3.0


def test_tool_call_retries_transient_sqlite_lock_and_succeeds():
    """Every real agent tool call goes through ``tool_call``. A transient SQLite
    lock (a genuine failure mode for this app's per-request connections) must be
    retried and recovered, not surfaced as a hard failure on the first attempt.
    """

    calls = {"count": 0}

    def flaky_operation():
        calls["count"] += 1
        if calls["count"] < 2:
            raise sqlite3.OperationalError("database is locked")
        return {"status": "recovered", "call_number": calls["count"]}

    state = {"thread_id": "retry-thread", "retry_count": 0}
    value, event = tool_call(
        state,
        node="task_analysis",
        agent="TaskAnalysisAgent",
        tool_name="flaky_sqlite_op",
        operation=flaky_operation,
    )

    assert value == {"status": "recovered", "call_number": 2}
    assert event["success"] is True
    assert calls["count"] == 2


def test_tool_call_does_not_retry_non_transient_errors():
    calls = {"count": 0}

    def always_invalid():
        calls["count"] += 1
        raise ValueError("not a transient failure")

    state = {"thread_id": "retry-thread-2", "retry_count": 0}
    with pytest.raises(ValueError):
        tool_call(
            state,
            node="task_analysis",
            agent="TaskAnalysisAgent",
            tool_name="invalid_op",
            operation=always_invalid,
        )

    assert calls["count"] == 1
