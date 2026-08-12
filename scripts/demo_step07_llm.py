"""Step 07 function-calling demonstration.

Without an API key this script runs a deterministic fake model trajectory while
executing the *real* SQLite-backed UniFlow tools. This validates the provider
protocol and security boundaries but is intentionally labeled non-live evidence.
For final capstone evidence, set LLM_PROVIDER=openai, LLM_MODEL and
OPENAI_API_KEY, then execute the normal workflow/API with LangGraph installed.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from prometheus_client import generate_latest

from app.llm import OpenAIResponsesCoordinator
from app.observability import Observability
from app.persistence import Database
from app.tools import StudyTools


class FakeResponses:
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            output = [
                SimpleNamespace(type="function_call", name="get_courses", call_id="call-1", arguments="{}"),
                SimpleNamespace(type="function_call", name="get_tasks", call_id="call-2", arguments="{}"),
                SimpleNamespace(type="function_call", name="get_availability_windows", call_id="call-3", arguments="{}"),
            ]
            return SimpleNamespace(
                id="fake-response-1",
                output=output,
                output_text="",
                usage=SimpleNamespace(input_tokens=25, output_tokens=12),
            )
        return SimpleNamespace(
            id="fake-response-2",
            output=[],
            output_text="Persisted student context inspected; continue to task analysis and planning.",
            usage=SimpleNamespace(input_tokens=40, output_tokens=14),
        )


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


def main() -> None:
    with TemporaryDirectory() as tmp:
        base = Path(tmp)
        db = Database(base / "demo.sqlite")
        db.initialize()
        tools = StudyTools(db)
        course = tools.add_course("demo-student", code="CEN 351", name="Signals", credit_hours=3)
        tools.add_task(
            "demo-student",
            title="Capstone task",
            course_id=course["id"],
            deadline="2026-08-14T20:00:00+00:00",
            estimated_hours=2,
            difficulty=4,
            user_priority="high",
        )
        tools.set_availability(
            "demo-student", study_date="2026-08-13", start_time="18:00", end_time="21:00"
        )
        observer = Observability(log_path=base / "llm.jsonl")
        agent = OpenAIResponsesCoordinator(
            client=FakeClient(), tools=tools, model="gpt-test-protocol", observer=observer
        )
        result = agent.run(
            {
                "thread_id": "step07-demo",
                "user_id": "demo-student",
                "user_request": "Create my study plan",
                "retry_count": 0,
            }
        )
        print("EVIDENCE_TYPE=PROTOCOL_TEST_NOT_LIVE_PROVIDER")
        print("llm_calls=", result.llm_calls)
        print("tool_calls=", json.dumps(result.tool_calls, ensure_ascii=False))
        print("courses_loaded=", len(result.tool_results["get_courses"]))
        print("tasks_loaded=", len(result.tool_results["get_tasks"]))
        print("availability_loaded=", len(result.tool_results["get_availability_windows"]))
        print("summary=", result.summary)
        metrics = generate_latest(observer.registry).decode()
        for line in metrics.splitlines():
            if line.startswith("uniflow_llm_calls_total") or line.startswith("uniflow_tool_calls_total"):
                print(line)


if __name__ == "__main__":
    main()
