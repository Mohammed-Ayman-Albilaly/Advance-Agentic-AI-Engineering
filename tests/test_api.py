from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config import Settings
from app.observability import Observability
from app.persistence import Database


def make_client(tmp_path):
    settings = Settings(
        APP_ENV="test",
        DATABASE_PATH=tmp_path / "api.sqlite",
        CHECKPOINT_DATABASE_PATH=tmp_path / "checkpoints.sqlite",
    )
    db = Database(settings.database_path)
    obs = Observability(log_path=tmp_path / "api.jsonl")
    return TestClient(create_app(settings=settings, database=db, observability=obs)), obs


def test_health_endpoint_and_metrics_are_exposed(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "uniflow_api_requests_total" in metrics.text
        assert 'route="/health"' in metrics.text


def test_course_task_availability_round_trip(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        course = client.post(
            "/courses",
            json={"user_id": "student-1", "code": "cen 351", "name": "Signals", "credit_hours": 3},
        )
        assert course.status_code == 201
        course_data = course.json()
        assert course_data["code"] == "CEN 351"

        task = client.post(
            "/tasks",
            json={
                "user_id": "student-1",
                "title": "Assignment 1",
                "course_id": course_data["id"],
                "deadline": "2026-08-14T20:00:00+00:00",
                "estimated_hours": 2,
                "difficulty": 3,
                "user_priority": "high",
            },
        )
        assert task.status_code == 201

        availability = client.post(
            "/availability",
            json={"user_id": "student-1", "date": "2026-08-13", "start_time": "18:00", "end_time": "21:00"},
        )
        assert availability.status_code == 201

        assert len(client.get("/courses", params={"user_id": "student-1"}).json()) == 1
        assert len(client.get("/tasks", params={"user_id": "student-1"}).json()) == 1
        assert len(client.get("/availability", params={"user_id": "student-1"}).json()) == 1


def test_cross_user_task_creation_is_rejected(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        course = client.post(
            "/courses",
            json={"user_id": "student-a", "code": "CSC 227", "name": "OS", "credit_hours": 3},
        ).json()
        result = client.post(
            "/tasks",
            json={
                "user_id": "student-b",
                "title": "Foreign task",
                "course_id": course["id"],
                "deadline": "2026-08-14T20:00:00+00:00",
                "estimated_hours": 1,
                "difficulty": 2,
                "user_priority": "medium",
            },
        )
        assert result.status_code == 409


def test_workflow_endpoint_fails_safely_when_langgraph_is_unavailable(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        response = client.post(
            "/workflow/start",
            json={"user_id": "student-1", "user_request": "Create my study plan"},
        )
        # In this restricted execution sandbox LangGraph cannot be installed.
        # In a normal project install this endpoint executes the real StateGraph.
        assert response.status_code in {200, 503}
        if response.status_code == 503:
            assert "LangGraph" in response.json()["detail"]


def test_api_logs_are_json_lines(tmp_path):
    client, obs = make_client(tmp_path)
    with client:
        client.get("/health")
    lines = obs.log_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines
    import json
    parsed = [json.loads(line) for line in lines]
    assert any(item.get("event") == "api_request" for item in parsed)


@pytest.mark.skipif(
    importlib.util.find_spec("langgraph") is None,
    reason="LangGraph dependency unavailable in this execution sandbox",
)
def test_full_api_workflow_reaches_interrupt_and_resumes_to_completion(tmp_path):
    """Drives the real production surface: FastAPI -> real LangGraph graph ->
    real interrupt() -> real Command(resume=...) -> persisted approved plan.
    Dates are computed relative to the real clock so this stays deterministic
    no matter when the suite runs.
    """

    client, _ = make_client(tmp_path)
    with client:
        course = client.post(
            "/courses",
            json={"user_id": "api-student", "code": "CEN 351", "name": "Signals", "credit_hours": 3},
        ).json()
        now = datetime.now(timezone.utc)
        window_date = (now + timedelta(days=2)).date().isoformat()
        deadline = (now + timedelta(days=3)).isoformat()
        client.post(
            "/tasks",
            json={
                "user_id": "api-student",
                "title": "API workflow task",
                "course_id": course["id"],
                "deadline": deadline,
                "estimated_hours": 2,
                "difficulty": 3,
                "user_priority": "high",
            },
        )
        client.post(
            "/availability",
            json={
                "user_id": "api-student",
                "date": window_date,
                "start_time": "18:00",
                "end_time": "21:00",
            },
        )

        started = client.post(
            "/workflow/start",
            json={"user_id": "api-student", "user_request": "Create my study plan"},
        )
        assert started.status_code == 200
        body = started.json()
        thread_id = body["thread_id"]
        assert body["status"] == "awaiting_approval"
        assert body["interrupt"]["type"] == "study_plan_approval"

        fetched = client.get(f"/workflow/{thread_id}", params={"user_id": "api-student"})
        assert fetched.status_code == 200
        assert fetched.json()["status"] == "awaiting_approval"

        resumed = client.post(
            f"/workflow/{thread_id}/resume",
            json={"user_id": "api-student", "decision": "approved"},
        )
        assert resumed.status_code == 200
        resumed_body = resumed.json()
        assert resumed_body["status"] == "completed"
        assert resumed_body["state"]["approval_status"] == "approved"

        plan = client.get(f"/plans/{thread_id}", params={"user_id": "api-student"})
        assert plan.status_code == 200
        assert plan.json()["status"] == "approved"


def test_unknown_task_status_update_returns_404(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        response = client.patch(
            "/tasks/missing/status",
            json={"user_id": "student-1", "status": "done"},
        )
        assert response.status_code == 404
