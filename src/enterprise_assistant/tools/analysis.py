"""Validate the input shape for a future bounded analytics tool.

The Pydantic model restricts operations, field length, and numeric input
count. It does not perform analysis or execute Python code.
"""

from pydantic import BaseModel, ConfigDict, Field


class AnalysisRequest(BaseModel):
    """Validate the bounded input shape for future analytics.

    The model permits only count, sum, or average, limits the field label,
    and caps numeric inputs at one thousand. It does not evaluate data or
    execute Python expressions.

    Attributes:
        operation: One supported aggregation name.
        field: Data field label supplied by a future caller.
        values: Bounded numeric values to analyze.
    """
    model_config = ConfigDict(extra="forbid")

    operation: str = Field(pattern="^(count|sum|average)$")
    field: str = Field(min_length=1, max_length=80)
    values: list[float] = Field(max_length=1000)
