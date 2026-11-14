"""Guardrail extension points; concrete model-facing policies are deferred."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    code: str
    message: str


class InputGuardrail(Protocol):
    async def inspect(self, text: str, *,
                      user_id: str) -> GuardrailDecision: ...


class OutputGuardrail(Protocol):
    async def inspect(self, text: str, *,
                      citation_ids: frozenset[str]) -> GuardrailDecision: ...
