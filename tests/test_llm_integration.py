from __future__ import annotations

from types import SimpleNamespace

import pytest
from prometheus_client import generate_latest

from app.agents import CoordinatorAgent
from app.config import Settings
from app.llm import (
    FunctionCallingProtocolError,
    LLMConfigurationError,
    OpenAIResponsesCoordinator,
    build_openai_coordinator,
)
from app.observability import Observability
from app.persistence import Database
from app.tools import StudyTools


class FakeResponses:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("unexpected extra LLM call")
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.responses = FakeResponses(responses)


def response(response_id, output, output_text="", input_tokens=10, output_tokens=5):
    return SimpleNamespace(
        id=response_id,
        output=output,
        output_text=output_text,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def function_call(name, call_id, arguments="{}"):
    return SimpleNamespace(type="function_call", name=name, call_id=call_id, arguments=arguments)


def seed(tmp_path):
    db = Database(tmp_path / "llm.sqlite")
    db.initialize()
    tools = StudyTools(db)
    course = tools.add_course("student-1", code="CEN 351", name="Signals", credit_hours=3)
    tools.add_task(
        "student-1",
        title="Assignment",
        course_id=course["id"],
        deadline="2026-08-14T20:00:00+00:00",
        estimated_hours=2,
        difficulty=3,
        user_priority="high",
    )
    tools.set_availability(
        "student-1", study_date="2026-08-13", start_time="18:00", end_time="21:00"
    )
    return tools


def test_openai_function_calling_executes_real_required_tools_and_synthesizes(tmp_path):
    tools = seed(tmp_path)
    observer = Observability(log_path=tmp_path / "llm.jsonl")
    client = FakeClient(
        [
            response(
                "resp-1",
                [
                    function_call("get_courses", "call-courses"),
                    function_call("get_tasks", "call-tasks"),
                    function_call("get_availability_windows", "call-availability"),
                ],
            ),
            response(
                "resp-2",
                [],
                output_text="Context inspected. Analyze deadlines, capacity, and then construct the plan.",
            ),
        ]
    )
    agent = OpenAIResponsesCoordinator(
        client=client, tools=tools, model="gpt-test", observer=observer
    )
    state = {
        "thread_id": "thread-llm",
        "user_id": "student-1",
        "user_request": "Create my study plan",
        "retry_count": 0,
    }

    result = agent.run(state)

    assert result.llm_calls == 2
    assert len(result.tool_results["get_courses"]) == 1
    assert len(result.tool_results["get_tasks"]) == 1
    assert len(result.tool_results["get_availability_windows"]) == 1
    assert {event["tool_name"] for event in result.tool_events} == {
        "get_courses",
        "get_tasks",
        "get_availability_windows",
    }
    assert all(event["success"] for event in result.tool_events)
    assert all(event["details"]["source"] == "openai_function_call" for event in result.tool_events)
    assert client.responses.calls[0]["tool_choice"] == "required"
    assert client.responses.calls[1]["tool_choice"] == "none"
    assert client.responses.calls[0]["store"] is False
    assert client.responses.calls[1]["store"] is False
    assert any(
        item.get("type") == "function_call_output"
        for item in client.responses.calls[1]["input"]
        if isinstance(item, dict)
    )
    assert "Context inspected" in result.summary

    metrics = generate_latest(observer.registry).decode()
    assert 'uniflow_llm_calls_total{agent="CoordinatorAgent",model="gpt-test",provider="openai",success="true"} 2.0' in metrics
    assert 'uniflow_llm_tokens_total{agent="CoordinatorAgent",direction="input",model="gpt-test",provider="openai"} 20.0' in metrics


def test_model_cannot_choose_user_id_or_other_arguments(tmp_path):
    tools = seed(tmp_path)
    client = FakeClient(
        [
            response(
                "resp-attack",
                [function_call("get_tasks", "call-attack", '{"user_id":"student-2"}')],
            )
        ]
    )
    agent = OpenAIResponsesCoordinator(client=client, tools=tools, model="gpt-test")
    state = {
        "thread_id": "thread-attack",
        "user_id": "student-1",
        "user_request": "plan",
        "retry_count": 0,
    }
    with pytest.raises(FunctionCallingProtocolError, match="does not accept model-controlled arguments"):
        agent.run(state)


def test_model_cannot_finish_before_required_context_tools(tmp_path):
    tools = seed(tmp_path)
    client = FakeClient([response("resp-stop", [], output_text="I am done")])
    agent = OpenAIResponsesCoordinator(client=client, tools=tools, model="gpt-test")
    with pytest.raises(FunctionCallingProtocolError, match="required tools"):
        agent.run(
            {
                "thread_id": "thread-stop",
                "user_id": "student-1",
                "user_request": "plan",
                "retry_count": 0,
            }
        )


def test_coordinator_marks_llm_function_calling_mode(tmp_path):
    tools = seed(tmp_path)
    fake_result = SimpleNamespace(
        tool_results={
            "get_courses": tools.get_courses("student-1"),
            "get_tasks": tools.get_tasks("student-1", include_done=False),
            "get_availability_windows": tools.get_availability_windows("student-1"),
        },
        tool_events=[],
        summary="Use the persisted context.",
        provider="openai",
        model="gpt-test",
        llm_calls=2,
    )
    fake_llm = SimpleNamespace(run=lambda state: fake_result)
    result = CoordinatorAgent(tools, llm_coordinator=fake_llm).run(
        {
            "thread_id": "t",
            "user_id": "student-1",
            "user_request": "Create my study plan",
            "retry_count": 0,
        }
    )
    assert result["coordination_mode"] == "llm_function_calling"
    assert result["llm_provider"] == "openai"
    assert result["llm_model"] == "gpt-test"
    assert result["llm_calls"] == 2
    assert result["agent_messages"][0]["payload"]["coordination_mode"] == "llm_function_calling"


def test_openai_selected_without_key_fails_closed(tmp_path):
    settings = Settings(
        LLM_PROVIDER="openai",
        LLM_MODEL="gpt-5.5",
        OPENAI_API_KEY="",
        DATABASE_PATH=tmp_path / "app.sqlite",
        CHECKPOINT_DATABASE_PATH=tmp_path / "cp.sqlite",
    )
    db = Database(settings.database_path)
    db.initialize()
    tools = StudyTools(db)
    with pytest.raises(LLMConfigurationError, match="OPENAI_API_KEY"):
        build_openai_coordinator(settings=settings, tools=tools)
