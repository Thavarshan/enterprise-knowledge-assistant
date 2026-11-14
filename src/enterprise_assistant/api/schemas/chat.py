"""Session and chat message contracts."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from enterprise_assistant.memory.models import ChatMessage, ChatSession


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=120)


class SessionResponse(BaseModel):
    session_id: str
    title: str
    created_at: str

    @classmethod
    def from_record(cls, session: ChatSession) -> "SessionResponse":
        return cls(
            session_id=session.session_id,
            title=session.title,
            created_at=session.created_at,
        )


class MessageResponse(BaseModel):
    message_id: int
    role: str
    content: str
    created_at: str

    @classmethod
    def from_record(cls, message: ChatMessage) -> "MessageResponse":
        return cls(
            message_id=message.message_id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )


class SessionDetailResponse(SessionResponse):
    messages: list[MessageResponse]


class ChatStreamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("message must contain non-whitespace text")
        return cleaned
