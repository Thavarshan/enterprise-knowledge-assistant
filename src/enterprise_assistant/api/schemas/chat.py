"""Define session and chat request and response contracts.

The schemas cap user-controlled text lengths, reject extra fields, and strip
whitespace from chat messages before route execution. Response conversion
keeps internal persistence records separate from HTTP representations.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from enterprise_assistant.memory.models import ChatMessage, ChatSession


class CreateSessionRequest(BaseModel):
    """Validate the optional title for a new session.

    Extra fields are rejected and title length is bounded before storage.

    Attributes:
        title: Optional display label; the store supplies a default.
    """
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=120)


class SessionResponse(BaseModel):
    """Represent a session in the HTTP API.

    Attributes:
        session_id: Owner-scoped conversation identifier.
        title: Display title persisted for the conversation.
        created_at: ISO-formatted creation timestamp.
    """
    session_id: str
    title: str
    created_at: str

    @classmethod
    def from_record(cls, session: ChatSession) -> "SessionResponse":
        """Convert the persistence record into the API schema.

        Args:
            session: Adapter-neutral stored session record.

        Returns:
            Public session representation without the internal owner ID.
        """
        return cls(
            session_id=session.session_id,
            title=session.title,
            created_at=session.created_at,
        )


class MessageResponse(BaseModel):
    """Represent one persisted message in a session response.

    Attributes:
        message_id: Monotonic database identifier within the store.
        role: User or assistant message role.
        content: Stored message text.
        created_at: ISO-formatted message timestamp.
    """
    message_id: int
    role: str
    content: str
    created_at: str

    @classmethod
    def from_record(cls, message: ChatMessage) -> "MessageResponse":
        """Convert a stored message to its public schema.

        Args:
            message: Adapter-neutral persisted message record.

        Returns:
            Public message representation.
        """
        return cls(
            message_id=message.message_id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )


class SessionDetailResponse(SessionResponse):
    """Represent a session together with its message history.

    The response inherits the public session fields and appends messages in
    persistence order.

    Attributes:
        messages: Ordered user and assistant message records.
    """
    messages: list[MessageResponse]


class ChatStreamRequest(BaseModel):
    """Validate a chat turn before the SSE endpoint runs.

    Extra fields are rejected, IDs and message sizes are bounded, and the
    validator trims surrounding whitespace before route execution.

    Attributes:
        session_id: Existing session identifier to which the turn belongs.
        message: Nonblank user text stored and passed to the graph.
    """
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        """Trim the message and reject whitespace-only content.

        Args:
            value: Raw message supplied to the request model.

        Returns:
            Message with surrounding whitespace removed.

        Raises:
            ValueError: The value contains no non-whitespace characters.
        """
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("message must contain non-whitespace text")
        return cleaned
