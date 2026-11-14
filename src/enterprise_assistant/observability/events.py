"""Stable, safe-to-display event contract for graph activity and SSE."""

import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal[
    "agent_transition",
    "retrieval",
    "tool_execution",
    "memory_update",
    "validation",
    "response_chunk",
    "completed",
    "failure",
]


class ActivityEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    request_id: str
    session_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent: str | None = None
    node: str | None = None
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


def encode_sse(event: ActivityEvent) -> str:
    event_name = event.event_type
    payload = json.dumps(event.model_dump(mode="json"), separators=(",", ":"))
    return f"event: {event_name}\ndata: {payload}\n\n"
