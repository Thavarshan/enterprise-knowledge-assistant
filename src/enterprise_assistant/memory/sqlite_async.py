"""Expose the SQLite repository through the async session-store contract.

Each synchronous SQLite operation runs in a worker thread. This keeps the
local persistence implementation unchanged while allowing services to use
one asynchronous interface for local and remote stores.
"""

import asyncio

from enterprise_assistant.memory.interfaces import SessionStore
from enterprise_assistant.memory.models import (
    ChatMessage,
    ChatSession,
    MessageRole,
)
from enterprise_assistant.memory.sqlite import SQLiteSessionStore


class AsyncSQLiteSessionStore:
    """Adapt the synchronous SQLite repository to ``SessionStore``.

    Attributes:
        repository: The existing synchronous, owner-scoped SQLite store.
    """

    def __init__(self, repository: SQLiteSessionStore) -> None:
        """Keep the synchronous repository behind this async adapter.

        Args:
            repository: Configured SQLite implementation.
        """
        self.repository = repository

    async def initialize(self) -> None:
        """Create local tables without blocking the event loop.

        The existing synchronous initializer runs in a worker thread.
        """
        await asyncio.to_thread(self.repository.initialize)

    async def healthcheck(self) -> bool:
        """Run the SQLite health check in a worker thread.

        The boolean result follows the shared session-store contract.
        """
        return await asyncio.to_thread(self.repository.healthcheck)

    async def create_session(
        self, owner_id: str, title: str | None = None
    ) -> ChatSession:
        """Create an owner-scoped session off the event loop.

        Args:
            owner_id: Authenticated account identifier.
            title: Optional conversation title.

        Returns:
            Newly persisted conversation.
        """
        return await asyncio.to_thread(
            self.repository.create_session,
            owner_id,
            title,
        )

    async def get_session(
        self, session_id: str, owner_id: str
    ) -> ChatSession | None:
        """Fetch an owner-scoped session off the event loop.

        Args:
            session_id: Conversation identifier.
            owner_id: Authenticated account identifier.

        Returns:
            The conversation, or None when it is inaccessible.
        """
        return await asyncio.to_thread(
            self.repository.get_session,
            session_id,
            owner_id,
        )

    async def list_messages(
        self, session_id: str, owner_id: str
    ) -> list[ChatMessage] | None:
        """Read ordered owner-scoped history off the event loop.

        Args:
            session_id: Conversation identifier.
            owner_id: Authenticated account identifier.

        Returns:
            Ordered history, or None when the conversation is inaccessible.
        """
        return await asyncio.to_thread(
            self.repository.list_messages,
            session_id,
            owner_id,
        )

    async def append_message(
        self,
        session_id: str,
        owner_id: str,
        role: MessageRole,
        content: str,
    ) -> ChatMessage:
        """Persist one message off the event loop.

        Args:
            session_id: Conversation identifier.
            owner_id: Authenticated account identifier.
            role: User or assistant message role.
            content: Message text to store.

        Returns:
            Persisted message record.

        Raises:
            LookupError: The session is missing or owned by another user.
        """
        return await asyncio.to_thread(
            self.repository.append_message,
            session_id,
            owner_id,
            role,
            content,
        )


def build_sqlite_store(database_path: str) -> SessionStore:
    """Build SQLite behind the application's asynchronous store interface.

    Args:
        database_path: SQLite file path or ``:memory:`` marker.

    Returns:
        Async adapter implementing the common persistence protocol.
    """
    return AsyncSQLiteSessionStore(SQLiteSessionStore(database_path))
