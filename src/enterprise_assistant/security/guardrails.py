"""Declare interfaces for future input and output guardrails.

The protocols describe asynchronous inspection boundaries and a structured
decision result. No prompt-injection classifier, exfiltration policy, or
output sanitizer currently implements or invokes them.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GuardrailDecision:
    """Represent an allow or reject result from a guardrail.

    Attributes:
        allowed: Whether the inspected input or output may continue.
        code: Stable decision identifier for logs or events.
        message: Safe concise explanation for the decision.
    """
    allowed: bool
    code: str
    message: str


class InputGuardrail(Protocol):
    """Specify an async inspection boundary for user input.

    Implementations may report a decision but must not replace backend
    authorization. No input guardrail implementation is currently invoked.
    """

    async def inspect(self, text: str, *,
                      user_id: str) -> GuardrailDecision:
        """Inspect user text in the context of a user identity.

        Args:
            text: Untrusted user-provided content.
            user_id: Server-resolved principal associated with the request.

        Returns:
            Structured allow or reject decision.
        """
        ...


class OutputGuardrail(Protocol):
    """Specify an async inspection boundary for generated output.

    The current deterministic response path uses citation validation
    separately; this protocol is not wired into the graph.
    """

    async def inspect(self, text: str, *,
                      citation_ids: frozenset[str]) -> GuardrailDecision:
        """Inspect response text against allowed citation IDs.

        Args:
            text: Candidate response before it is shown to the user.
            citation_ids: Evidence identifiers accepted for this turn.

        Returns:
            Structured allow or reject decision.
        """
        ...
