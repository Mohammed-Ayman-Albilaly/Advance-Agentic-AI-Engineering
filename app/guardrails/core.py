"""Enforced input/output guardrails for UniFlow AI."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import StudyPlan


class GuardrailDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    status: str
    reason: str
    matched_rules: list[str] = Field(default_factory=list)


class OutputGuardrailResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    status: str
    reason: str
    sanitized_output: dict[str, Any] | None = None
    redactions: int = 0
    blocked_fields: list[str] = Field(default_factory=list)


class InputGuardrail:
    """Detect explicit attempts to override control instructions or exfiltrate data.

    The rules are intentionally narrow: educational discussion about prompt injection
    is allowed, while imperative attempts to override safeguards, reveal protected
    prompts/secrets, or bypass human approval are blocked.
    """

    _RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
        (
            "instruction_override",
            re.compile(
                r"\b(ignore|disregard|forget|override)\b.{0,80}"
                r"\b(previous|prior|system|developer|security|safety)\b.{0,40}"
                r"\b(instruction|instructions|rule|rules|prompt|prompts)\b",
                re.IGNORECASE | re.DOTALL,
            ),
        ),
        (
            "protected_prompt_exfiltration",
            re.compile(
                r"\b(reveal|show|print|display|expose|leak|give me)\b.{0,80}"
                r"\b(system prompt|developer message|developer prompt|hidden prompt|"
                r"api key|secret|password|stored student data|all stored data)\b",
                re.IGNORECASE | re.DOTALL,
            ),
        ),
        (
            "control_bypass",
            re.compile(
                r"\b(bypass|skip|disable|remove|circumvent)\b.{0,80}"
                r"\b(approval|human approval|guardrail|security|safety|policy|reviewer)\b",
                re.IGNORECASE | re.DOTALL,
            ),
        ),
    )

    def inspect(self, text: str) -> GuardrailDecision:
        normalized = " ".join((text or "").split())
        matched = [name for name, pattern in self._RULES if pattern.search(normalized)]
        if matched:
            return GuardrailDecision(
                allowed=False,
                status="blocked",
                reason="Potential prompt-injection or control-bypass attempt detected.",
                matched_rules=matched,
            )
        return GuardrailDecision(
            allowed=True,
            status="passed",
            reason="No enforced prompt-injection rule matched.",
            matched_rules=[],
        )


class OutputGuardrail:
    """Validate final plan structure and remove sensitive user-facing data."""

    _FORBIDDEN_KEYS = {
        "system_prompt",
        "developer_prompt",
        "developer_message",
        "api_key",
        "openai_api_key",
        "password",
        "secret",
        "access_token",
        "refresh_token",
    }
    _EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
    _PHONE = re.compile(r"(?<!\d)(?:\+?966|0)?5\d{8}(?!\d)")

    def _scan_forbidden_keys(self, value: Any, *, path: str = "") -> list[str]:
        found: list[str] = []
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if str(key).casefold() in self._FORBIDDEN_KEYS:
                    found.append(child_path)
                found.extend(self._scan_forbidden_keys(child, path=child_path))
        elif isinstance(value, list):
            for idx, child in enumerate(value):
                found.extend(self._scan_forbidden_keys(child, path=f"{path}[{idx}]"))
        return found

    def _mask(self, value: Any) -> tuple[Any, int]:
        if isinstance(value, str):
            value, email_count = self._EMAIL.subn("<EMAIL_REDACTED>", value)
            value, phone_count = self._PHONE.subn("<PHONE_REDACTED>", value)
            return value, email_count + phone_count
        if isinstance(value, list):
            result: list[Any] = []
            count = 0
            for item in value:
                masked, item_count = self._mask(item)
                result.append(masked)
                count += item_count
            return result, count
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            count = 0
            for key, item in value.items():
                masked, item_count = self._mask(item)
                result[key] = masked
                count += item_count
            return result, count
        return value, 0

    def protect_plan(self, output: dict[str, Any]) -> OutputGuardrailResult:
        blocked_fields = self._scan_forbidden_keys(output)
        if blocked_fields:
            return OutputGuardrailResult(
                allowed=False,
                status="blocked",
                reason="Output contains forbidden internal or secret-bearing fields.",
                blocked_fields=blocked_fields,
            )

        sanitized, redactions = self._mask(deepcopy(output))
        try:
            validated = StudyPlan.model_validate(sanitized)
        except Exception as exc:
            return OutputGuardrailResult(
                allowed=False,
                status="blocked",
                reason=f"Output failed StudyPlan schema validation: {type(exc).__name__}",
                redactions=redactions,
            )

        return OutputGuardrailResult(
            allowed=True,
            status="passed",
            reason="Output passed schema validation and data-protection checks.",
            sanitized_output=validated.model_dump(mode="json"),
            redactions=redactions,
        )
