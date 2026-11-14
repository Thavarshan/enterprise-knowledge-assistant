"""Provide deterministic prompt-injection checks and guardrail contracts.

The input guard blocks clear instruction-override and credential-exfiltration
requests before they are stored or sent to a model. It supplements server
authorization and structured tool validation; it is not a general-purpose
semantic classifier.
"""

import re
from dataclasses import dataclass
from typing import Protocol

_OVERRIDE_PATTERN = re.compile(
    r"\b(?:ignore|disregard|override|forget)\b"
    r"[\s\S]{0,80}\b(?:all\s+)?(?:previous|prior|above|system|developer)\b"
    r"[\s\S]{0,40}\b(?:instructions?|prompts?|rules?)\b",
    re.IGNORECASE,
)
_EXFILTRATION_PATTERN = re.compile(
    r"\b(?:show|print|dump|reveal|expose|exfiltrate|send|export)\b"
    r"[\s\S]{0,80}\b(?:api[\s_-]*keys?|secrets?|credentials?|"
    r"passwords?|access tokens?|system prompts?)\b",
    re.IGNORECASE,
)


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


class PromptInjectionGuardrail:
    """Reject explicit instruction overrides and secret-exfiltration asks.

    The application still treats documents and history as untrusted model
    data. This guard focuses on obvious user-message attack patterns; tool
    schemas and backend authorization remain the effective control boundary.
    """

    async def inspect(
        self,
        text: str,
        *,
        user_id: str,
    ) -> GuardrailDecision:
        """Check one user message before it is persisted or model-bound.

        Args:
            text: Untrusted user message, already bounded by the API schema.
            user_id: Server-resolved principal; policy is currently global.

        Returns:
            Safe allow or reject decision without echoing the message.
        """
        del user_id
        if _OVERRIDE_PATTERN.search(text):
            return GuardrailDecision(
                allowed=False,
                code="instruction_override_blocked",
                message=(
                    "This message was rejected by the input security policy."
                ),
            )
        if _EXFILTRATION_PATTERN.search(text):
            return GuardrailDecision(
                allowed=False,
                code="credential_exfiltration_blocked",
                message=(
                    "This message was rejected by the input security policy."
                ),
            )
        return GuardrailDecision(
            allowed=True,
            code="input_allowed",
            message="",
        )
