"""Execute Step 03 real-tool and retry scenarios for captured evidence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.persistence import Database
from app.tools import StudyTools, TransientToolError, execute_with_retry


DEMO_DB = Path("data/step03_demo.sqlite")
NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def emit(label: str, value) -> None:
    print(json.dumps({"step": label, "result": value}, ensure_ascii=False, default=str))


def main() -> None:
    if DEMO_DB.exists():
        DEMO_DB.unlink()
    db = Database(DEMO_DB)
    db.initialize()
    tools = StudyTools(db, clock=lambda: NOW)

    course = tools.add_course(
        "evidence-student",
        code="CEN 351",
        name="Signals and Systems",
        credit_hours=3,
    )
    emit("add_course", course)

    task = tools.add_task(
        "evidence-student",
        title="Capstone planning exercise",
        course_id=course["id"],
        deadline="2026-08-13T12:00:00+00:00",
        estimated_hours=4,
        difficulty=4,
        user_priority="high",
    )
    emit("add_task", task)

    tools.set_availability(
        "evidence-student",
        study_date="2026-08-13",
        start_time="18:00",
        end_time="21:00",
    )
    emit("available_hours", tools.get_available_hours("evidence-student"))
    emit("priority_analysis", tools.calculate_task_priority(task))
    emit("deadline_conflicts", tools.check_deadline_conflicts("evidence-student"))

    calls = {"count": 0}

    def simulated_transient_tool():
        calls["count"] += 1
        if calls["count"] == 1:
            raise TransientToolError("simulated temporary resource lock")
        return {"status": "recovered", "call_number": calls["count"]}

    retry = execute_with_retry(simulated_transient_tool, max_attempts=2)
    emit(
        "transient_failure_retry",
        {"attempts": retry.attempts, "value": retry.value},
    )

    DEMO_DB.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
