"""Step 6 executable evidence: real tool logs, metrics, and FastAPI requests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from app.agents import CoordinatorAgent
from app.api.main import create_app
from app.config import Settings
from app.observability import Observability, set_observability
from app.persistence import Database
from app.tools import StudyTools


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
EVIDENCE = ROOT / "evidence"
DB_PATH = DATA / "step06-demo.sqlite"
LOG_PATH = EVIDENCE / "step06-structured.jsonl"

for path in (DB_PATH, LOG_PATH):
    if path.exists():
        path.unlink()

observer = Observability(log_path=LOG_PATH)
set_observability(observer)
db = Database(DB_PATH)
db.initialize()
tools = StudyTools(db)

course = tools.add_course("demo-student", code="CEN 351", name="Signals and Systems", credit_hours=3)
tools.add_task(
    "demo-student",
    title="Signals assignment",
    course_id=course["id"],
    deadline="2026-08-14T20:00:00+00:00",
    estimated_hours=2,
    difficulty=3,
    user_priority="high",
)
tools.set_availability(
    "demo-student",
    study_date="2026-08-13",
    start_time="18:00",
    end_time="21:00",
)

state = {
    "thread_id": "step06-demo-thread",
    "user_id": "demo-student",
    "user_request": "Create my study plan",
    "retry_count": 0,
}
coordinated = CoordinatorAgent(tools).run(state)
print("REAL_TOOL_CALLS:", [event["tool_name"] for event in coordinated["tool_events"]])
print("TOOL_CALL_SUCCESS:", all(event["success"] for event in coordinated["tool_events"]))

settings = Settings(
    APP_ENV="test",
    DATABASE_PATH=DB_PATH,
    CHECKPOINT_DATABASE_PATH=DATA / "step06-demo-checkpoints.sqlite",
    LOG_PATH=LOG_PATH,
)
app = create_app(settings=settings, database=db, observability=observer)
with TestClient(app) as client:
    health = client.get("/health")
    metrics = client.get("/metrics")
    print("HEALTH_STATUS:", health.status_code, health.json())
    print("METRICS_STATUS:", metrics.status_code)

metric_text = generate_latest(observer.registry).decode()
selected = [
    line
    for line in metric_text.splitlines()
    if line.startswith("uniflow_tool_calls_total")
    or line.startswith("uniflow_api_requests_total")
]
print("PROMETHEUS_SAMPLE:")
for line in selected:
    print(line)

log_lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
print("STRUCTURED_LOG_LINES:", len(log_lines))
print("STRUCTURED_LOG_SAMPLE:", log_lines[0])
