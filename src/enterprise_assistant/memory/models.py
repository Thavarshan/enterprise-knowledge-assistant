"""Stable session persistence records shared by adapters and services."""

from dataclasses import dataclass
from typing import Literal

MessageRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class ChatSession:
    session_id: str
    owner_id: str
    title: str
    created_at: str


@dataclass(frozen=True)
class ChatMessage:
    message_id: int
    session_id: str
    role: MessageRole
    content: str
    created_at: str
