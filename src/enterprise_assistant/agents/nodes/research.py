"""Restricted structured search planning used by the Research graph node."""

from enterprise_assistant.rlm.contracts import (
    ExecutionBudget,
    SearchPlan,
    interpret_search_plan,
    plan_queries,
)


def plan_research(
    question: str,
) -> tuple[SearchPlan, tuple[str, ...], ExecutionBudget]:
    """Create one approved query under fixed execution budgets."""
    plan = plan_queries(question, max_queries=1)
    budget = ExecutionBudget(max_depth=1, max_search_calls=1, max_documents=5)
    return plan, interpret_search_plan(plan, budget), budget
