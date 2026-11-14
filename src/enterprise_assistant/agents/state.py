"""Typed shared state for the minimal executable agent graph."""

import operator
from typing import Annotated, Any, Literal

from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    request_id: str
    session_id: str
    user_id: str
    role: str
    question: str
    route: Literal["retrieval", "research"]
    search_plan: dict[str, Any]
    results: list[dict[str, Any]]
    response: str
    citations: list[dict[str, str]]
    validation_passed: bool
    events: Annotated[list[dict[str, Any]], operator.add]
