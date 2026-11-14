"""Structured search plans that replace execution of model-generated Python."""

from pydantic import BaseModel, ConfigDict, Field


class TaskDecomposition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    objective: str = Field(min_length=1, max_length=1000)
    subtasks: list[str] = Field(min_length=1, max_length=4)


class SearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    queries: list[str] = Field(min_length=1, max_length=4)
    max_depth: int = Field(default=1, ge=0, le=2)


class ExecutionBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_depth: int = Field(default=1, ge=0, le=2)
    max_search_calls: int = Field(default=1, ge=1, le=4)
    max_documents: int = Field(default=5, ge=1, le=20)
    timeout_seconds: int = Field(default=15, ge=1, le=60)


class BatchAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    summaries: list[str] = Field(max_length=20)
    conclusion: str = ""


def plan_queries(question: str, *, max_queries: int = 1) -> SearchPlan:
    """Create a tiny plan; model-proposed Python is never executed."""
    bounded_count = max(1, min(max_queries, 4))
    return SearchPlan(queries=[question][:bounded_count], max_depth=1)


def interpret_search_plan(
    plan: SearchPlan, budget: ExecutionBudget
) -> tuple[str, ...]:
    """Interpret validated query strings under a hard search-call budget."""
    if plan.max_depth > budget.max_depth:
        raise ValueError("search plan exceeds the configured depth budget")
    return tuple(plan.queries[: budget.max_search_calls])
