"""Prepare the bounded structured plan used by the Research node.

The current planner wraps the question in a validated `SearchPlan` and
limits execution to one query, one search call, one depth level, and five
documents. It does not call a model or recursively decompose the question.
"""

from enterprise_assistant.rlm.contracts import (
    ExecutionBudget,
    SearchPlan,
    interpret_search_plan,
    plan_queries,
)


def plan_research(
    question: str,
) -> tuple[SearchPlan, tuple[str, ...], ExecutionBudget]:
    """Prepare the single-query plan used by the Research node.

    The question is wrapped in a validated SearchPlan, then interpreted
    under fixed depth, call, document, and timeout values. No recursive
    scheduler exists.

    Args:
        question: Validated question to search for evidence.

    Returns:
        The plan, permitted query tuple, and associated budget.
    """
    plan = plan_queries(question, max_queries=1)
    budget = ExecutionBudget(max_depth=1, max_search_calls=1, max_documents=5)
    return plan, interpret_search_plan(plan, budget), budget
