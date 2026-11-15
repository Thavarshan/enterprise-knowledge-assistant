"""Persist sessions and messages in a local SQLite database.

Each operation opens a short-lived connection, uses parameterized SQL, and
includes `owner_id` in session access queries. Foreign keys cascade message
deletes. Database calls are synchronous and use a five-second connection
timeout; async service boundaries offload them to worker threads.
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from enterprise_assistant.memory.models import (
    ChatMessage,
    ChatSession,
    MessageRole,
)


class SQLiteSessionStore:
    """Persist owner-scoped chat sessions and messages in SQLite.

    The store opens one synchronous connection per operation and creates the
    parent directory for file-backed databases. SQL parameters protect
    values from injection; every session lookup and append includes owner
    identity. The adapter is intended for the demo and modest local use,
    not high-latency production storage.

    Attributes:
        database_path: SQLite filename or the special in-memory path.

    Concurrency:
        Connections are operation-local. The store is synchronous; API and
        chat service callers offload database calls from the event loop.
    """

    def __init__(self, database_path: str) -> None:
        """Set the database path used by each operation.

        Args:
            database_path: File path or SQLite in-memory database marker.
        """
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        """Open a configured connection and ensure its parent exists.

        Returns:
            Connection with row mappings and foreign-key enforcement
            enabled.

        Notes:
            The caller owns and must close the returned connection.
        """
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        """Create session and message tables and their lookup indexes.

        The schema enforces valid message roles and cascades message deletion
        when a session is removed.
        """
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_owner_idx
                    ON sessions(owner_id);
                CREATE TABLE IF NOT EXISTS messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL
                        REFERENCES sessions(session_id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_session_idx
                    ON messages(session_id, message_id);
                """
            )

    def healthcheck(self) -> bool:
        """Run a minimal query to check database availability.

        Returns:
            True when SQLite accepts a query; False for SQLite errors.
        """
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def create_session(
        self, owner_id: str, title: str | None = None
    ) -> ChatSession:
        """Create and persist a new session for an owner.

        Empty or missing titles become New conversation. The database
        assigns no session ID; this method generates a UUID before insert.

        Args:
            owner_id: Trusted authenticated user ID.
            title: Optional title supplied by the API.

        Returns:
            The session record inserted into the database.
        """
        session = ChatSession(
            session_id=str(uuid4()),
            owner_id=owner_id,
            title=(title or "New conversation").strip() or "New conversation",
            created_at=datetime.now(UTC).isoformat(),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO sessions("
                "session_id, owner_id, title, created_at"
                ") VALUES (?, ?, ?, ?)",
                (session.session_id, session.owner_id,
                 session.title, session.created_at),
            )
        return session

    def list_sessions(self, owner_id: str) -> list[ChatSession]:
        """List the newest sessions belonging to one owner.

        Args:
            owner_id: Trusted authenticated user ID.

        Returns:
            Up to 100 owner-scoped sessions, newest first.
        """
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT session_id, owner_id, title, created_at "
                "FROM sessions WHERE owner_id = ? "
                "ORDER BY created_at DESC, session_id DESC LIMIT 100",
                (owner_id,),
            ).fetchall()
        return [ChatSession(**dict(row)) for row in rows]

    def get_session(self, session_id: str, owner_id: str) -> ChatSession | None:
        """Fetch a session only for its authenticated owner.

        Args:
            session_id: Session identifier to query.
            owner_id: Authenticated user ID.

        Returns:
            Session record or None for missing and foreign-owned sessions.
        """
        with self._connect() as connection:
            row = connection.execute(
                "SELECT session_id, owner_id, title, created_at FROM sessions "
                "WHERE session_id = ? AND owner_id = ?",
                (session_id, owner_id),
            ).fetchone()
        return ChatSession(**dict(row)) if row else None

    def list_messages(
        self, session_id: str, owner_id: str
    ) -> list[ChatMessage] | None:
        """Read messages only after confirming session ownership.

        Args:
            session_id: Session whose history is requested.
            owner_id: Authenticated user ID.

        Returns:
            Ordered message records, or None if the session is inaccessible.
        """
        with self._connect() as connection:
            owns_session = connection.execute(
                "SELECT 1 FROM sessions WHERE session_id = ? AND owner_id = ?",
                (session_id, owner_id),
            ).fetchone()
            if owns_session is None:
                return None
            rows = connection.execute(
                "SELECT message_id, session_id, role, content, created_at "
                "FROM messages "
                "WHERE session_id = ? ORDER BY message_id",
                (session_id,),
            ).fetchall()
        return [
            ChatMessage(
                message_id=row["message_id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def append_message(
        self, session_id: str, owner_id: str, role: MessageRole, content: str
    ) -> ChatMessage:
        """Insert a message after checking session ownership.

        Ownership lookup and insert occur within the same connection
        context.
        A missing or foreign-owned session fails before content is written.

        Args:
            session_id: Destination session identifier.
            owner_id: Authenticated owner.
            role: User or assistant role.
            content: Message text to persist.

        Returns:
            The stored message with its generated row ID.

        Raises:
            LookupError: No session exists for this owner.
            RuntimeError: SQLite does not return the inserted row ID.
        """
        created_at = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            owner = connection.execute(
                "SELECT 1 FROM sessions WHERE session_id = ? AND owner_id = ?",
                (session_id, owner_id),
            ).fetchone()
            if owner is None:
                raise LookupError("Session does not exist for this user.")
            cursor = connection.execute(
                "INSERT INTO messages("
                "session_id, role, content, created_at"
                ") VALUES (?, ?, ?, ?)",
                (session_id, role, content, created_at),
            )
            if cursor.lastrowid is None:
                raise RuntimeError(
                    "SQLite did not return the inserted message ID.")
            message_id = cursor.lastrowid
        return ChatMessage(
            message_id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            created_at=created_at,
        )
