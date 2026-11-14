"""Define the activity-event schema and its server-sent-event encoding.

Events carry request and session correlation, an event type, a concise
message, and structured metadata. The schema is intended for execution
status and evidence references, not chain-of-thought or secret values.
"""

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
    """Describe one user-visible graph or service activity.

    Events expose coarse execution status, correlation IDs, and optional
    structured evidence references. They are not graph snapshots and must
    not contain model chain-of-thought or secret values.

    Attributes:
        event_type: Stable category such as retrieval or validation.
        request_id: Request correlation identifier.
        session_id: Conversation identifier.
        timestamp: UTC creation time by default.
        agent: Optional logical agent label.
        node: Optional graph node or service boundary.
        message: Concise status text rendered by the UI.
        metadata: Structured status fields or source references.
    """
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
    """Serialize an activity event as one server-sent-event record.

    The event type becomes the SSE event name and the complete validated
    model is JSON-encoded as the data payload.

    Args:
        event: Validated event to serialize.

    Returns:
        UTF-8-compatible SSE text ending with a blank line.
    """
    event_name = event.event_type
    payload = json.dumps(event.model_dump(mode="json"), separators=(",", ":"))
    return f"event: {event_name}\ndata: {payload}\n\n"
