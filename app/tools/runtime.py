"""Execution helpers for real UniFlow tools.

The retry helper is intentionally framework-agnostic so graph nodes can reuse it.
Only explicitly transient failures are retried; validation, authorization, and
integrity errors fail immediately.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar


T = TypeVar("T")


class ToolExecutionError(RuntimeError):
    """Base exception for a tool execution failure."""


class TransientToolError(ToolExecutionError):
    """Failure that may succeed when the same operation is retried."""


class RetryExhaustedError(ToolExecutionError):
    """Raised after a transient tool failure exceeds the retry budget."""


@dataclass(frozen=True)
class RetryOutcome(Generic[T]):
    """Result of a successful retryable execution."""

    value: T
    attempts: int


def execute_with_retry(
    operation: Callable[[], T],
    *,
    max_attempts: int = 2,
    delay_seconds: float = 0.0,
) -> RetryOutcome[T]:
    """Execute an operation and retry only :class:`TransientToolError`.

    This creates a deterministic failure/retry path that can be exercised in
    tests and later from the LangGraph workflow. Non-transient errors are never
    hidden by a retry.
    """

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if delay_seconds < 0:
        raise ValueError("delay_seconds cannot be negative")

    last_error: TransientToolError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return RetryOutcome(value=operation(), attempts=attempt)
        except TransientToolError as exc:
            last_error = exc
            if attempt < max_attempts and delay_seconds:
                time.sleep(delay_seconds)

    raise RetryExhaustedError(
        f"tool failed after {max_attempts} attempts: {last_error}"
    ) from last_error
