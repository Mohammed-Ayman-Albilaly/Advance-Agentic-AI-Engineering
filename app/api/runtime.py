"""Lazy LangGraph runtime used by FastAPI workflow endpoints."""

from __future__ import annotations

import importlib.util
from typing import Any
from uuid import uuid4

from app.config import Settings
from app.graph.workflow import build_workflow
from app.llm import LLMConfigurationError, build_openai_coordinator
from app.observability import get_observability
from app.persistence import SqliteCheckpointResource
from app.tools import StudyTools


class RuntimeDependencyError(RuntimeError):
    """Raised when an optional runtime dependency is unavailable or misconfigured."""


class WorkflowRuntime:
    def __init__(
        self,
        tools: StudyTools,
        checkpoint_path,
        *,
        max_replans: int = 3,
        settings: Settings | None = None,
    ) -> None:
        self.tools = tools
        self.checkpoint_path = checkpoint_path
        self.max_replans = max_replans
        self.settings = settings
        self._checkpoint: SqliteCheckpointResource | None = None
        self._graph: Any | None = None

    def _ensure_graph(self):
        if self._graph is not None:
            return self._graph
        if importlib.util.find_spec("langgraph") is None:
            raise RuntimeDependencyError(
                "LangGraph runtime dependency is unavailable. Install project requirements first."
            )

        llm_coordinator = None
        if self.settings is not None:
            try:
                llm_coordinator = build_openai_coordinator(
                    settings=self.settings,
                    tools=self.tools,
                    observer=get_observability(),
                )
            except LLMConfigurationError as exc:
                raise RuntimeDependencyError(str(exc)) from exc

        self._checkpoint = SqliteCheckpointResource(self.checkpoint_path)
        saver = self._checkpoint.open()
        self._graph = build_workflow(
            self.tools,
            max_replans=self.max_replans,
            checkpointer=saver,
            llm_coordinator=llm_coordinator,
        )
        return self._graph

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    @staticmethod
    def _interrupt_payload(result: Any) -> dict[str, Any] | None:
        if not isinstance(result, dict):
            return None
        raw = result.get("__interrupt__")
        if not raw:
            return None
        first = raw[0] if isinstance(raw, (list, tuple)) else raw
        value = getattr(first, "value", first)
        return value if isinstance(value, dict) else {"value": str(value)}

    def start(self, *, user_id: str, user_request: str, thread_id: str | None = None) -> dict[str, Any]:
        graph = self._ensure_graph()
        thread_id = thread_id or str(uuid4())
        state = {
            "thread_id": thread_id,
            "user_id": user_id,
            "user_request": user_request,
            "retry_count": 0,
            "tool_events": [],
            "agent_messages": [],
            "graph_trace": [],
            "errors": [],
        }
        result = graph.invoke(state, config=self._config(thread_id))
        return self._response(thread_id, result)

    def get_state(self, *, thread_id: str, user_id: str) -> dict[str, Any]:
        graph = self._ensure_graph()
        snapshot = graph.get_state(self._config(thread_id))
        values = dict(getattr(snapshot, "values", {}) or {})
        if values and values.get("user_id") != user_id:
            raise PermissionError("workflow does not belong to this user")
        # ``StateSnapshot.interrupts`` is a separate field from ``values`` (unlike
        # the dict returned by ``graph.invoke()``, which embeds ``__interrupt__``
        # directly). Re-attach it so a client polling this endpoint while paused
        # sees the same "awaiting_approval" status as the original invoke/resume.
        interrupts = getattr(snapshot, "interrupts", None)
        if interrupts and values:
            values["__interrupt__"] = interrupts
        return self._response(thread_id, values)

    def resume(
        self,
        *,
        thread_id: str,
        user_id: str,
        decision: str,
        feedback: str | None = None,
    ) -> dict[str, Any]:
        graph = self._ensure_graph()
        current = self.get_state(thread_id=thread_id, user_id=user_id)
        if not current["state"]:
            raise KeyError("workflow thread not found")
        from langgraph.types import Command

        payload: dict[str, Any] = {"decision": decision}
        if feedback:
            payload["feedback"] = feedback
        result = graph.invoke(Command(resume=payload), config=self._config(thread_id))
        return self._response(thread_id, result)

    def _response(self, thread_id: str, result: Any) -> dict[str, Any]:
        state = dict(result) if isinstance(result, dict) else {}
        interrupt = self._interrupt_payload(state)
        status = "awaiting_approval" if interrupt else str(state.get("workflow_status", "running"))
        state.pop("__interrupt__", None)
        return {
            "thread_id": thread_id,
            "status": status,
            "state": state,
            "interrupt": interrupt,
        }

    def close(self) -> None:
        if self._checkpoint is not None:
            self._checkpoint.close()
        self._checkpoint = None
        self._graph = None
