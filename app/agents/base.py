"""Shared helpers for specialized UniFlow AI agents."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable, TypeVar

from app.graph.state import StudyState
from app.observability import get_observability

T = TypeVar("T")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def tool_call(
    state: StudyState,
    *,
    node: str,
    agent: str,
    tool_name: str,
    operation: Callable[[], T],
    details: dict[str, Any] | None = None,
) -> tuple[T, dict[str, Any]]:
    """Execute one real tool and return a structured event for shared state.

    Step 5 adds durable logs/metrics. This event object is already structured so
    every agent handoff and tool invocation is inspectable in graph state.
    """

    started = perf_counter()
    try:
        value = operation()
    except Exception as exc:
        elapsed = round((perf_counter() - started) * 1000, 3)
        event = {
            "timestamp": utc_now().isoformat(),
            "thread_id": state.get("thread_id", ""),
            "node": node,
            "agent": agent,
            "tool_name": tool_name,
            "success": False,
            "latency_ms": elapsed,
            "retry_count": int(state.get("retry_count", 0)),
            "details": {**(details or {}), "error_type": type(exc).__name__},
        }
        # Keep the original exception semantics; callers decide whether to retry.
        setattr(exc, "uniflow_tool_event", event)
        get_observability().record_tool_event(event)
        raise

    elapsed = round((perf_counter() - started) * 1000, 3)
    event = {
        "timestamp": utc_now().isoformat(),
        "thread_id": state.get("thread_id", ""),
        "node": node,
        "agent": agent,
        "tool_name": tool_name,
        "success": True,
        "latency_ms": elapsed,
        "retry_count": int(state.get("retry_count", 0)),
        "details": dict(details or {}),
    }
    get_observability().record_tool_event(event)
    return value, event


def message(
    *,
    sender: str,
    recipient: str,
    message_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Create a structured inter-agent message stored in shared state."""

    return {
        "timestamp": utc_now().isoformat(),
        "sender": sender,
        "recipient": recipient,
        "type": message_type,
        "payload": payload,
    }
