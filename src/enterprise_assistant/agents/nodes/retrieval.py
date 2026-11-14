"""Select only a validated query from the bounded graph search plan."""

from typing import Any


def selected_query(question: str, plan: dict[str, Any] | None) -> str:
    """Return the sole bounded query or fall back to the user question."""
    queries = plan.get("queries", []) if plan is not None else []
    return str(queries[0]) if queries else question
