from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.graph.hitl import apply_approval_decision, approval_request_payload


def _state() -> dict:
    now = datetime(2026, 8, 12, 18, 0, tzinfo=timezone.utc).isoformat()
    return {
        "thread_id": "hitl-thread",
        "user_id": "student-1",
        "proposed_plan": {
            "thread_id": "hitl-thread",
            "user_id": "student-1",
            "status": "draft",
            "sessions": [],
            "summary": "Reviewed proposal",
            "created_at": now,
            "updated_at": now,
        },
        "reviewer_feedback": [],
        "retry_count": 0,
    }


def test_approval_payload_is_json_serializable_shape():
    payload = approval_request_payload(_state())
    assert payload["type"] == "study_plan_approval"
    assert payload["thread_id"] == "hitl-thread"
    assert payload["allowed_decisions"] == ["approved", "rejected"]
    assert payload["plan"]["status"] == "draft"


def test_human_approval_promotes_plan_to_final_approved_plan():
    update = apply_approval_decision(_state(), {"decision": "approved"})
    assert update["approval_status"] == "approved"
    assert update["final_plan"]["status"] == "approved"
    assert update["workflow_status"] == "human_approved"


def test_human_rejection_requires_feedback_and_triggers_replan():
    state = _state()
    update = apply_approval_decision(
        state,
        {"decision": "rejected", "feedback": "Thursday is too busy."},
    )
    assert update["approval_status"] == "rejected"
    assert update["approval_feedback"] == "Thursday is too busy."
    assert update["retry_count"] == 1
    assert update["workflow_status"] == "human_rejected_replan_required"


def test_human_rejection_without_feedback_is_invalid():
    with pytest.raises(ValidationError):
        apply_approval_decision(_state(), {"decision": "rejected"})
