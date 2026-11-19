"""Define immutable session and message records used across layers.

The records carry owner identity and timestamps alongside persisted content.
They are adapter-neutral values, not HTTP schemas or authentication tokens.
"""

from dataclasses import dataclass
from typing import Literal

MessageRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class ChatSession:
    """Represent a persisted conversation and its owner.

    This frozen adapter-neutral record is used between the memory and API
    layers. Owner identity remains internal and is checked by the store.

    Attributes:
        session_id: Generated conversation identifier.
        owner_id: User ID that owns the session.
        title: Display title.
        created_at: ISO-formatted UTC creation time.
    """

    session_id: str
    owner_id: str
    title: str
    created_at: str


@dataclass(frozen=True)
class ChatMessage:
    """Represent one persisted user or assistant message.

    The frozen record is returned in history order and converted separately
    to an HTTP response schema.

    Attributes:
        message_id: Store-assigned message identifier.
        session_id: Owning conversation identifier.
        role: Whether the message came from the user or assistant.
        content: Persisted message text.
        created_at: ISO-formatted UTC creation time.
    """

    message_id: int
    session_id: str
    role: MessageRole
    content: str
    created_at: str
