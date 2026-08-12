import json

from prometheus_client import generate_latest

from app.observability import Observability


def test_structured_tool_log_and_metrics_are_real(tmp_path):
    obs = Observability(log_path=tmp_path / "events.jsonl")
    obs.record_tool_event(
        {
            "timestamp": "2026-08-12T18:00:00+00:00",
            "thread_id": "thread-1",
            "node": "coordinator",
            "agent": "CoordinatorAgent",
            "tool_name": "get_tasks",
            "success": True,
            "latency_ms": 12.5,
            "retry_count": 0,
            "details": {},
        }
    )

    line = (tmp_path / "events.jsonl").read_text(encoding="utf-8").strip()
    parsed = json.loads(line)
    assert parsed["event"] == "tool_call"
    assert parsed["tool_name"] == "get_tasks"
    assert parsed["latency_ms"] == 12.5

    metrics = generate_latest(obs.registry).decode()
    assert 'uniflow_tool_calls_total{success="true",tool_name="get_tasks"} 1.0' in metrics
    assert "uniflow_tool_latency_seconds_count" in metrics


def test_guardrail_replan_approval_and_workflow_metrics(tmp_path):
    obs = Observability(log_path=tmp_path / "events.jsonl")
    obs.record_guardrail_block("input", "t", "attack")
    obs.record_replan("reviewer", "t")
    obs.record_approval("approved", "t")
    obs.record_workflow_outcome("completed", "t")
    text = generate_latest(obs.registry).decode()
    assert 'uniflow_guardrail_blocks_total{guardrail="input"} 1.0' in text
    assert 'uniflow_replans_total{source="reviewer"} 1.0' in text
    assert 'uniflow_approval_decisions_total{decision="approved"} 1.0' in text
    assert 'uniflow_workflow_executions_total{status="completed"} 1.0' in text


def test_llm_metrics_and_structured_log(tmp_path):
    obs = Observability(log_path=tmp_path / "llm-events.jsonl")
    obs.record_llm_call(
        provider="openai",
        model="gpt-test",
        agent="CoordinatorAgent",
        success=True,
        latency_seconds=0.25,
        input_tokens=120,
        output_tokens=30,
        thread_id="thread-1",
    )
    text = generate_latest(obs.registry).decode()
    assert 'uniflow_llm_calls_total{agent="CoordinatorAgent",model="gpt-test",provider="openai",success="true"} 1.0' in text
    assert 'direction="input"' in text
    lines = (tmp_path / "llm-events.jsonl").read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines]
    assert any(item.get("event") == "llm_call" and item.get("input_tokens") == 120 for item in parsed)
