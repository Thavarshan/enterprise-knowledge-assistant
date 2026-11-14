"""Select the query passed to the knowledge-search tool.

A query from the structured Research plan is used when present; otherwise
the original question is returned. The function does not execute a search or
trust a plan to grant access.
"""

from typing import Any


def selected_query(question: str, plan: dict[str, Any] | None) -> str:
    """Select the first query from a bounded search plan.

    If no plan or query is available, return the original question. A
    plan changes query wording only and cannot change access policy.

    Args:
        question: Original validated user question.
        plan: Optional graph plan containing query strings.

    Returns:
        The first planned query or the original question.
    """
    queries = plan.get("queries", []) if plan is not None else []
    return str(queries[0]) if queries else question
