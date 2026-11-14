"""SQLite session store with explicit owner scoping for every read and write."""

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
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
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
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def create_session(
        self, owner_id: str, title: str | None = None
    ) -> ChatSession:
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

    def get_session(self, session_id: str, owner_id: str) -> ChatSession | None:
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
