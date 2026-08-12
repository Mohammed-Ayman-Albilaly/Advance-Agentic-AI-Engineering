"""Structured logging and Prometheus metrics for UniFlow AI."""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any, Callable, TypeVar

from prometheus_client import CollectorRegistry, Counter, Histogram

T = TypeVar("T")


class JsonFormatter(logging.Formatter):
    """Render one JSON object per log record for machine-readable evidence."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        structured = getattr(record, "structured", None)
        if isinstance(structured, dict):
            payload.update(structured)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class Observability:
    """Own structured logs and a dedicated Prometheus registry.

    A dedicated registry avoids test/import duplication and keeps the metrics
    exported by UniFlow AI explicit and predictable.
    """

    def __init__(self, *, log_path: str | Path = "logs/uniflow.jsonl", log_level: str = "INFO") -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry = CollectorRegistry()
        self._logger = logging.getLogger(f"uniflow.{id(self)}")
        self._logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        self._logger.propagate = False
        self._logger.handlers.clear()
        handler = logging.handlers.RotatingFileHandler(
            self.log_path,
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(JsonFormatter())
        self._logger.addHandler(handler)

        self.workflow_executions = Counter(
            "uniflow_workflow_executions_total",
            "Total workflow terminal outcomes.",
            ["status"],
            registry=self.registry,
        )
        self.tool_calls = Counter(
            "uniflow_tool_calls_total",
            "Total real tool calls.",
            ["tool_name", "success"],
            registry=self.registry,
        )
        self.tool_latency = Histogram(
            "uniflow_tool_latency_seconds",
            "Tool execution latency in seconds.",
            ["tool_name"],
            registry=self.registry,
        )
        self.node_executions = Counter(
            "uniflow_node_executions_total",
            "Total graph-node executions.",
            ["node", "success"],
            registry=self.registry,
        )
        self.node_latency = Histogram(
            "uniflow_node_latency_seconds",
            "Graph-node execution latency in seconds.",
            ["node"],
            registry=self.registry,
        )
        self.replans = Counter(
            "uniflow_replans_total",
            "Total reviewer/HITL re-planning routes.",
            ["source"],
            registry=self.registry,
        )
        self.guardrail_blocks = Counter(
            "uniflow_guardrail_blocks_total",
            "Total blocked guardrail decisions.",
            ["guardrail"],
            registry=self.registry,
        )
        self.approval_decisions = Counter(
            "uniflow_approval_decisions_total",
            "Total human approval decisions.",
            ["decision"],
            registry=self.registry,
        )
        self.api_requests = Counter(
            "uniflow_api_requests_total",
            "Total HTTP requests handled by the API.",
            ["method", "route", "status_code"],
            registry=self.registry,
        )
        self.api_latency = Histogram(
            "uniflow_api_request_latency_seconds",
            "HTTP request latency in seconds.",
            ["method", "route"],
            registry=self.registry,
        )
        self.llm_calls = Counter(
            "uniflow_llm_calls_total",
            "Total LLM API calls.",
            ["provider", "model", "agent", "success"],
            registry=self.registry,
        )
        self.llm_latency = Histogram(
            "uniflow_llm_latency_seconds",
            "LLM API latency in seconds.",
            ["provider", "model", "agent"],
            registry=self.registry,
        )
        self.llm_tokens = Counter(
            "uniflow_llm_tokens_total",
            "LLM tokens reported by the provider.",
            ["provider", "model", "agent", "direction"],
            registry=self.registry,
        )

    def log(self, event: str, **fields: Any) -> None:
        self._logger.info(event, extra={"structured": {"event": event, **fields}})

    def record_tool_event(self, event: dict[str, Any]) -> None:
        tool_name = str(event.get("tool_name") or "unknown")
        success = bool(event.get("success"))
        latency_ms = float(event.get("latency_ms") or 0.0)
        self.tool_calls.labels(tool_name=tool_name, success=str(success).lower()).inc()
        self.tool_latency.labels(tool_name=tool_name).observe(latency_ms / 1000)
        self.log("tool_call", **event)

    def record_node(
        self,
        *,
        node: str,
        thread_id: str,
        success: bool,
        latency_seconds: float,
        error_type: str | None = None,
    ) -> None:
        self.node_executions.labels(node=node, success=str(success).lower()).inc()
        self.node_latency.labels(node=node).observe(latency_seconds)
        self.log(
            "node_execution",
            node=node,
            thread_id=thread_id,
            success=success,
            latency_ms=round(latency_seconds * 1000, 3),
            error_type=error_type,
        )

    def record_replan(self, source: str, thread_id: str) -> None:
        self.replans.labels(source=source).inc()
        self.log("replan", source=source, thread_id=thread_id)

    def record_guardrail_block(self, guardrail: str, thread_id: str, reason: str) -> None:
        self.guardrail_blocks.labels(guardrail=guardrail).inc()
        self.log(
            "guardrail_block",
            guardrail=guardrail,
            thread_id=thread_id,
            reason=reason,
        )

    def record_approval(self, decision: str, thread_id: str) -> None:
        self.approval_decisions.labels(decision=decision).inc()
        self.log("human_approval", decision=decision, thread_id=thread_id)

    def record_workflow_outcome(self, status: str, thread_id: str) -> None:
        self.workflow_executions.labels(status=status).inc()
        self.log("workflow_outcome", status=status, thread_id=thread_id)

    def record_llm_call(
        self,
        *,
        provider: str,
        model: str,
        agent: str,
        success: bool,
        latency_seconds: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
        thread_id: str = "",
    ) -> None:
        success_label = str(bool(success)).lower()
        self.llm_calls.labels(
            provider=provider, model=model, agent=agent, success=success_label
        ).inc()
        self.llm_latency.labels(provider=provider, model=model, agent=agent).observe(
            latency_seconds
        )
        if input_tokens:
            self.llm_tokens.labels(
                provider=provider, model=model, agent=agent, direction="input"
            ).inc(input_tokens)
        if output_tokens:
            self.llm_tokens.labels(
                provider=provider, model=model, agent=agent, direction="output"
            ).inc(output_tokens)
        self.log(
            "llm_call",
            provider=provider,
            model=model,
            agent=agent,
            success=bool(success),
            latency_ms=round(latency_seconds * 1000, 3),
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            thread_id=thread_id,
        )

    def record_api_request(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        latency_seconds: float,
    ) -> None:
        self.api_requests.labels(
            method=method, route=route, status_code=str(status_code)
        ).inc()
        self.api_latency.labels(method=method, route=route).observe(latency_seconds)
        self.log(
            "api_request",
            method=method,
            route=route,
            status_code=status_code,
            latency_ms=round(latency_seconds * 1000, 3),
        )

    def observed_node(self, node: str, function: Callable[[Any], T]) -> Callable[[Any], T]:
        """Wrap a graph node with latency/failure metrics without changing semantics."""

        def wrapped(state: Any) -> T:
            started = perf_counter()
            thread_id = str(state.get("thread_id", "")) if isinstance(state, dict) else ""
            try:
                result = function(state)
            except Exception as exc:
                # LangGraph interrupt is normal control flow, not a node failure.
                if type(exc).__name__ in {"GraphInterrupt", "NodeInterrupt"}:
                    self.record_node(
                        node=node,
                        thread_id=thread_id,
                        success=True,
                        latency_seconds=perf_counter() - started,
                    )
                    self.log("node_interrupt", node=node, thread_id=thread_id)
                    raise
                self.record_node(
                    node=node,
                    thread_id=thread_id,
                    success=False,
                    latency_seconds=perf_counter() - started,
                    error_type=type(exc).__name__,
                )
                raise
            self.record_node(
                node=node,
                thread_id=thread_id,
                success=True,
                latency_seconds=perf_counter() - started,
            )
            return result

        return wrapped


_default_observability: Observability | None = None
_default_lock = Lock()


def get_observability(*, log_path: str | Path = "logs/uniflow.jsonl") -> Observability:
    global _default_observability
    with _default_lock:
        if _default_observability is None:
            _default_observability = Observability(log_path=log_path)
        return _default_observability


def set_observability(instance: Observability | None) -> None:
    """Override/reset the process-wide observer (primarily for app factories/tests)."""

    global _default_observability
    with _default_lock:
        _default_observability = instance
