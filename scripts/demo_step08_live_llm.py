"""Capture live OpenAI function-calling evidence for the final capstone gate.

Prerequisites:
- pip install -r requirements.txt
- LLM_PROVIDER=openai
- LLM_MODEL=<available model, e.g. gpt-5.5>
- OPENAI_API_KEY=<real key in local .env or environment>

The API key is never printed or written to evidence.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.llm import build_openai_coordinator
from app.observability import Observability
from app.persistence import Database
from app.tools import StudyTools

EVIDENCE = Path("evidence/step08_live_openai.txt")
DB_PATH = Path("data/step08_live_openai.sqlite")


def emit(lines: list[str]) -> None:
    text = "\n".join(lines) + "\n"
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(text, encoding="utf-8")
    print(text, end="")


def main() -> None:
    settings = Settings()
    if settings.llm_provider != "openai":
        raise SystemExit("Set LLM_PROVIDER=openai before running live OpenAI evidence.")
    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value().strip():
        raise SystemExit("OPENAI_API_KEY is not configured. Keep it only in .env/environment.")
    if not settings.llm_model.strip():
        raise SystemExit("LLM_MODEL is not configured.")

    DB_PATH.unlink(missing_ok=True)
    db = Database(DB_PATH)
    db.initialize()
    tools = StudyTools(db)
    observer = Observability(log_path=Path("logs/step08_live_openai.jsonl"))

    user_id = "step08-live-student"
    now = datetime.now(timezone.utc)
    course = tools.add_course(user_id, code="CEN 351", name="Signals and Systems", credit_hours=3)
    tools.add_task(
        user_id,
        title="Capstone live LLM evidence task",
        course_id=course["id"],
        deadline=now + timedelta(days=2),
        estimated_hours=2.0,
        difficulty=4,
        user_priority="high",
    )
    tools.set_availability(
        user_id,
        study_date=(now + timedelta(days=1)).date(),
        start_time="18:00",
        end_time="21:00",
    )

    coordinator = build_openai_coordinator(settings=settings, tools=tools, observer=observer)
    if coordinator is None:
        raise SystemExit("OpenAI coordinator was not created.")

    result = coordinator.run(
        {
            "thread_id": "step08-live-openai",
            "user_id": user_id,
            "user_request": "Inspect my persisted context and coordinate creation of a realistic study plan.",
            "retry_count": 0,
        }
    )
    called = [item["name"] for item in result.tool_calls]
    required = {"get_courses", "get_tasks", "get_availability_windows"}
    success = required.issubset(set(called)) and result.llm_calls >= 2

    lines = [
        "=== STEP 8 LIVE OPENAI FUNCTION-CALLING EVIDENCE ===",
        "provider=openai",
        f"model={result.model}",
        f"llm_calls={result.llm_calls}",
        "tool_calls=" + json.dumps(called, ensure_ascii=False),
        f"required_tools_executed={required.issubset(set(called))}",
        f"courses_loaded={len(result.tool_results.get('get_courses', []))}",
        f"tasks_loaded={len(result.tool_results.get('get_tasks', []))}",
        f"availability_loaded={len(result.tool_results.get('get_availability_windows', []))}",
        "summary=" + result.summary.replace("\n", " "),
        f"LIVE_OPENAI_SUCCESS={str(success).lower()}",
    ]
    emit(lines)
    if not success:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
