"""Define the asynchronous session persistence contract.

All application services depend on this async protocol. Local SQLite uses
thread offloading behind the same interface, while network-backed adapters
perform native asynchronous I/O.
"""

from typing import Protocol

from enterprise_assistant.memory.models import (
    ChatMessage,
    ChatSession,
    MessageRole,
)


class SessionStore(Protocol):
    """Specify the owner-scoped asynchronous persistence operations.

    Stores return None for missing or foreign-owned sessions and raise
    LookupError when an append targets a missing or foreign session.
    """

    async def initialize(self) -> None:
        """Prepare the store or verify remote schema readiness.

        Application startup calls this before serving requests.
        """
        ...

    async def healthcheck(self) -> bool:
        """Return whether the backing store can answer a health query.

        A false result indicates that persistence is currently unavailable.
        """
        ...

    async def create_session(
        self, owner_id: str, title: str | None = None
    ) -> ChatSession:
        """Create a conversation owned by an authenticated user.

        The returned record includes its generated session identifier.
        """
        ...

    async def list_sessions(
        self, owner_id: str
    ) -> list[ChatSession]:
        """List the most recent conversations owned by one user.

        Args:
            owner_id: Authenticated account identifier.

        Returns:
            The owner's sessions ordered newest first.
        """
        ...

    async def get_session(
        self, session_id: str, owner_id: str
    ) -> ChatSession | None:
        """Fetch a session only when the owner matches.

        Missing and foreign-owned sessions both return None.
        """
        ...

    async def list_messages(
        self, session_id: str, owner_id: str
    ) -> list[ChatMessage] | None:
        """Return ordered messages for an owned session.

        Missing and foreign-owned sessions both return None.
        """
        ...

    async def append_message(
        self,
        session_id: str,
        owner_id: str,
        role: MessageRole,
        content: str,
    ) -> ChatMessage:
        """Append a message to an owned session.

        Stores reject writes when the session is missing or foreign-owned.
        """
        ...
