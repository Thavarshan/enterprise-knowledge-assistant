"""Restricted analysis contract; arbitrary Python execution is excluded."""

from pydantic import BaseModel, ConfigDict, Field


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: str = Field(pattern="^(count|sum|average)$")
    field: str = Field(min_length=1, max_length=80)
    values: list[float] = Field(max_length=1000)
