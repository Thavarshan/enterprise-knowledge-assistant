"""Define the synchronous contract for session persistence.

Implementations initialize and check storage, create owner-scoped sessions,
read history, and append messages. These methods are synchronous; async
service boundaries must offload calls to avoid blocking the event loop.
"""

from typing import Protocol

from enterprise_assistant.memory.models import (
    ChatMessage,
    ChatSession,
    MessageRole,
)


class SessionStore(Protocol):
    """Specify the synchronous session persistence contract.

    Implementations must scope session reads and message writes by owner,
    return None for inaccessible sessions, and raise LookupError when an
    append targets a missing or foreign-owned session. Methods are
    synchronous; callers must account for blocking adapter behavior.

    Notes:
        The API and chat service use worker threads for these synchronous
        operations. A high-latency database should use a native async adapter.
    """

    def initialize(self) -> None:
        """Prepare storage structures before serving requests.

        Implementations create required tables or verify existing schema.
        """
        ...

    def healthcheck(self) -> bool:
        """Check whether the backing store can answer a basic health query.

        Returns:
            True when the store is ready; otherwise False.
        """
        ...

    def create_session(
        self, owner_id: str, title: str | None = None
    ) -> ChatSession:
        """Create a session owned by the supplied user.

        Args:
            owner_id: Trusted authenticated user ID.
            title: Optional display title.

        Returns:
            Newly persisted session record.
        """
        ...

    def get_session(
        self, session_id: str, owner_id: str
    ) -> ChatSession | None:
        """Fetch one session only when its owner matches.

        Args:
            session_id: Session identifier to locate.
            owner_id: Authenticated owner allowed to access it.

        Returns:
            The session record or None for missing and foreign-owned IDs.
        """
        ...

    def list_messages(
        self, session_id: str, owner_id: str
    ) -> list[ChatMessage] | None:
        """List a session's messages after verifying ownership.

        Args:
            session_id: Session whose history is requested.
            owner_id: Authenticated owner allowed to access it.

        Returns:
            Messages in store order, or None when inaccessible.
        """
        ...

    def append_message(
        self,
        session_id: str,
        owner_id: str,
        role: MessageRole,
        content: str,
    ) -> ChatMessage:
        """Append a message only to an owned session.

        Args:
            session_id: Destination session identifier.
            owner_id: Authenticated owner.
            role: User or assistant message role.
            content: Message text to persist.

        Returns:
            The persisted message record.

        Raises:
            LookupError: The session does not exist for this owner.
        """
        ...
