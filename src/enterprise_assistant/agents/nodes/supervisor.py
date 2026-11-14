"""Deterministic intent routing policy for the Supervisor graph node."""

from typing import Literal

Workflow = Literal["retrieval", "research"]


def select_workflow(question: str) -> Workflow:
    """Choose the bounded investigation path for explicit analysis requests."""
    normalized = question.casefold()
    if any(word in normalized for word in ("investigate", "compare", "analyze")):
        return "research"
    return "retrieval"
