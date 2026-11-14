"""Validate investigation plans and explicit execution-budget values.

Pydantic models reject extra fields and bound query counts, recursion depth,
search calls, retrieved documents, and elapsed execution time. The executor
uses these contracts to schedule model-proposed searches without running
model-generated code.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskDecomposition(BaseModel):
    """Represent a bounded objective and its proposed subtasks.

    The immutable model accepts one to four bounded, distinct strings and
    rejects extra fields. The executor may recursively expand these tasks
    within its configured depth and search budgets.

    Attributes:
        objective: Objective capped at 1,000 characters.
        subtasks: One to four proposed subtask strings, each at most 500
            characters.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    objective: str = Field(min_length=1, max_length=1000)
    subtasks: list[str] = Field(min_length=1, max_length=4)

    @field_validator("objective")
    @classmethod
    def normalize_objective(cls, value: str) -> str:
        """Trim the objective and reject whitespace-only values.

        Args:
            value: Proposed investigation objective.

        Returns:
            A non-empty trimmed objective.

        Raises:
            ValueError: The objective contains only whitespace.
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("objective must not be blank")
        return normalized

    @field_validator("subtasks")
    @classmethod
    def validate_subtasks(cls, values: list[str]) -> list[str]:
        """Trim, bound, and deduplicate proposed search subtasks.

        Args:
            values: Model-proposed search tasks.

        Returns:
            Distinct non-empty search tasks in model order.

        Raises:
            ValueError: A task is blank or exceeds 500 characters.
        """
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 500 for value in normalized):
            raise ValueError("subtasks must be non-empty and at most 500 chars")
        return list(dict.fromkeys(normalized))


class SearchPlan(BaseModel):
    """Represent search query strings and a bounded depth value.

    The immutable model accepts one to four bounded strings and depth from
    zero to two. The executor validates every decomposition before routing.

    Attributes:
        queries: One to four query strings, each at most 500 characters.
        max_depth: Requested depth bounded from zero to two.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    queries: list[str] = Field(min_length=1, max_length=4)
    max_depth: int = Field(default=1, ge=0, le=2)

    @field_validator("queries")
    @classmethod
    def validate_queries(cls, values: list[str]) -> list[str]:
        """Trim, bound, and deduplicate search query strings.

        Args:
            values: Proposed search query strings.

        Returns:
            Distinct non-empty query strings in their original order.

        Raises:
            ValueError: A query is blank or exceeds 500 characters.
        """
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 500 for value in normalized):
            raise ValueError("queries must be non-empty and at most 500 chars")
        return list(dict.fromkeys(normalized))


class ExecutionBudget(BaseModel):
    """Declare maximum research work for the plan interpreter.

    Pydantic validates depth, call, document, and timeout ranges. The
    executor enforces each bound across the complete investigation.

    Attributes:
        max_depth: Maximum recursive plan depth from zero to two.
        max_search_calls: Total allowed retrieval calls from one to four.
        max_documents: Total retrieved chunks from one to twenty.
        timeout_seconds: Wall-clock limit for the full investigation.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_depth: int = Field(default=1, ge=0, le=2)
    max_search_calls: int = Field(default=1, ge=1, le=4)
    max_documents: int = Field(default=5, ge=1, le=20)
    timeout_seconds: int = Field(default=15, ge=1, le=60)


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
    # The query slice enforces the plan's maximum retrieval-call count.
    return tuple(plan.queries[: budget.max_search_calls])
