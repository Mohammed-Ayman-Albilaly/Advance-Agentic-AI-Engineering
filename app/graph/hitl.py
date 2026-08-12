"""Pure helpers for LangGraph human-in-the-loop approval handling."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.graph.state import StudyState
from app.models import ApprovalDecision, ApprovalStatus, PlanStatus, StudyPlan


def approval_request_payload(state: StudyState) -> dict[str, Any]:
    """Build a JSON-serializable payload surfaced by ``interrupt()``."""

    plan = dict(state.get("proposed_plan") or {})
    return {
        "type": "study_plan_approval",
        "thread_id": state.get("thread_id", ""),
        "message": "Review the proposed study plan and approve or reject it.",
        "plan": plan,
        "reviewer_feedback": list(state.get("reviewer_feedback", [])),
        "allowed_decisions": ["approved", "rejected"],
    }


def apply_approval_decision(
    state: StudyState,
    raw_decision: dict[str, Any],
) -> dict[str, Any]:
    """Validate a human decision and return a state update.

    Rejection feedback is fed back into the planning loop. Approval promotes the
    reviewed draft to an approved final plan; persistence happens in a later node.
    """

    decision = ApprovalDecision.model_validate(raw_decision)
    if decision.decision == ApprovalStatus.APPROVED:
        now = datetime.now(timezone.utc)
        plan_data = dict(state.get("proposed_plan") or {})
        plan_data["status"] = PlanStatus.APPROVED.value
        plan_data["updated_at"] = now.isoformat()
        final_plan = StudyPlan.model_validate(plan_data).model_dump(mode="json")
        return {
            "approval_status": ApprovalStatus.APPROVED.value,
            "approval_feedback": decision.feedback or "",
            "final_plan": final_plan,
            "workflow_status": "human_approved",
        }

    feedback = decision.feedback or "Human rejected the proposed plan."
    return {
        "approval_status": ApprovalStatus.REJECTED.value,
        "approval_feedback": feedback,
        "reviewer_feedback": [feedback],
        "retry_count": int(state.get("retry_count", 0)) + 1,
        "workflow_status": "human_rejected_replan_required",
    }
