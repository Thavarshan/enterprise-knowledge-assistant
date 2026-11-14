"""Validate search plans and explicit execution-budget values.

Pydantic models reject extra fields and bound query counts, depth, calls,
document counts, and timeout values. The current graph uses a single
structured query; it does not execute model-generated Python or recursive
subtasks, and the timeout field is not yet enforced by a runtime.
"""

from pydantic import BaseModel, ConfigDict, Field


class TaskDecomposition(BaseModel):
    """Represent a bounded objective and its proposed subtasks.

    The immutable model accepts one to four strings and rejects extra
    fields. The current graph does not execute this contract.

    Attributes:
        objective: Objective capped at 1,000 characters.
        subtasks: One to four proposed subtask strings.

    Notes:
        This is a planning contract, not a recursive executor.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    objective: str = Field(min_length=1, max_length=1000)
    subtasks: list[str] = Field(min_length=1, max_length=4)


class SearchPlan(BaseModel):
    """Represent search query strings and a bounded depth value.

    The immutable model accepts one to four strings and depth from zero
    to two. The current Research path uses one query and depth one.

    Attributes:
        queries: One to four query strings.
        max_depth: Requested depth bounded from zero to two.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    queries: list[str] = Field(min_length=1, max_length=4)
    max_depth: int = Field(default=1, ge=0, le=2)


class ExecutionBudget(BaseModel):
    """Declare maximum research work for the plan interpreter.

    Pydantic validates depth, call, document, and timeout ranges.
    Runtime currently enforces depth and call count; document count
    becomes a result limit, while timeout_seconds is not enforced by a
    timer.

    Attributes:
        max_depth: Maximum plan depth from zero to two.
        max_search_calls: Allowed calls from one to four.
        max_documents: Result limit from one to twenty.
        timeout_seconds: Declared bound not wired to cancellation.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_depth: int = Field(default=1, ge=0, le=2)
    max_search_calls: int = Field(default=1, ge=1, le=4)
    max_documents: int = Field(default=5, ge=1, le=20)
    timeout_seconds: int = Field(default=15, ge=1, le=60)


class BatchAnalysis(BaseModel):
    """Represent intermediate summaries and a batch conclusion.

    The immutable model caps the summary list at twenty items. No
    current node batches documents or consumes this result type.

    Attributes:
        summaries: Zero to twenty summary strings.
        conclusion: Optional aggregate conclusion text.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    summaries: list[str] = Field(max_length=20)
    conclusion: str = ""


def plan_queries(question: str, *, max_queries: int = 1) -> SearchPlan:
    """Create a SearchPlan containing the original question.

    Clamp the requested count to one through four, then slice the
    current one-item input list. This keeps the initial planner bounded
    without model-generated query expansion.

    Args:
        question: Question to retain as the initial query.
        max_queries: Requested maximum, clamped to the supported range.

    Returns:
        A validated plan with depth one and at most one query.
    """
    bounded_count = max(1, min(max_queries, 4))
    return SearchPlan(queries=[question][:bounded_count], max_depth=1)


def interpret_search_plan(
    plan: SearchPlan, budget: ExecutionBudget
) -> tuple[str, ...]:
    """Apply the execution budget to a validated search plan.

    Raise ValueError when the plan depth exceeds the budget. Otherwise,
    return only the first max_search_calls query strings.

    Args:
        plan: Validated query plan from the Research node.
        budget: Validated upper bounds for this planning step.

    Returns:
        An immutable tuple of permitted query strings.

    Raises:
        ValueError: The plan requests depth above the budget.
    """
    if plan.max_depth > budget.max_depth:
        raise ValueError("search plan exceeds the configured depth budget")
    # The query slice enforces call count; elapsed time is not enforced here.
    return tuple(plan.queries[: budget.max_search_calls])
