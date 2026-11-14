"""Replaceable session persistence contract."""

from typing import Protocol

from enterprise_assistant.memory.models import (
    ChatMessage,
    ChatSession,
    MessageRole,
)


class SessionStore(Protocol):
    def initialize(self) -> None: ...

    def healthcheck(self) -> bool: ...

    def create_session(self, owner_id: str, title: str |
                       None = None) -> ChatSession: ...

    def get_session(self, session_id: str,
                    owner_id: str) -> ChatSession | None: ...

    def list_messages(self, session_id: str,
                      owner_id: str) -> list[ChatMessage] | None: ...

    def append_message(
        self, session_id: str, owner_id: str, role: MessageRole, content: str
    ) -> ChatMessage: ...
