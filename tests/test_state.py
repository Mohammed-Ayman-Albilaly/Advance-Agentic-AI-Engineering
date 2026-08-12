from typing import get_type_hints

from app.graph.state import StudyState


def test_shared_state_contains_required_capstone_fields() -> None:
    hints = get_type_hints(StudyState, include_extras=True)
    required = {
        "thread_id",
        "user_request",
        "courses",
        "tasks",
        "availability",
        "analyzed_tasks",
        "proposed_plan",
        "conflicts",
        "review_status",
        "retry_count",
        "approval_status",
        "final_plan",
        "guardrail_status",
        "tool_events",
        "errors",
    }
    assert required.issubset(hints.keys())
