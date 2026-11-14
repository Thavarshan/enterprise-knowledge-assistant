"""Verify synchronous session storage is offloaded from the event loop.

The fake store blocks deliberately so a chat run can prove the API keeps
serving async tasks and preserves cancellation at its coroutine boundary.
"""

import asyncio
from pathlib import Path
from threading import Event
from typing import cast
from uuid import uuid4

import pytest

from enterprise_assistant.chat.service import ChatService
from enterprise_assistant.memory.models import ChatMessage
from enterprise_assistant.memory.sqlite import SQLiteSessionStore
from enterprise_assistant.memory.sqlite_async import (
    AsyncSQLiteSessionStore,
)
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever
from enterprise_assistant.security.authentication import AuthenticatedUser
from enterprise_assistant.security.authorization import Role
from enterprise_assistant.tools.registry import ToolRegistry


class BlockingSessionStore:
    """Simulate a synchronous database call that waits on a worker thread.

    Thread events let the test control when the fake call returns.
    """

    def __init__(self) -> None:
        """Prepare thread coordination for a blocking history read.

        The worker signals start and waits until the test releases it.
        """
        self.started = Event()
        self.release = Event()

    def list_messages(
        self,
        session_id: str,
        owner_id: str,
    ) -> list[ChatMessage]:
        """Block briefly, then return empty owner-scoped history.

        Args:
            session_id: Session identifier, unused by the fixture.
            owner_id: Owner identifier, unused by the fixture.

        Returns:
            Empty conversation history after the test releases the call.
        """
        del session_id, owner_id
        self.started.set()
        self.release.wait(timeout=5)
        return []

    def append_message(
        self,
        session_id: str,
        owner_id: str,
        role: str,
        content: str,
    ) -> None:
        """Accept the final assistant message without database work.

        Args:
            session_id: Session identifier, unused by the fixture.
            owner_id: Authenticated owner, unused by the fixture.
            role: Message role, unused by the fixture.
            content: Message content, unused by the fixture.
        """
        del session_id, owner_id, role, content


@pytest.mark.asyncio
async def test_blocking_session_read_does_not_stall_the_event_loop() -> None:
    """Keep async tasks responsive while a synchronous history read waits.

    The memory adapter simulates a slow SQLite operation in ``to_thread``.
    """
    memory = BlockingSessionStore()
    async_memory = AsyncSQLiteSessionStore(
        cast(SQLiteSessionStore, memory)
    )
    service = ChatService(
        InMemoryRetriever([]),
        async_memory,
        ToolRegistry(),
    )
    user = AuthenticatedUser(user_id="viewer", role=Role.VIEWER)

    async def consume_turn() -> list[object]:
        """Drain one deterministic chat turn to completion.

        Returns:
            Activity events produced by the graph and service.
        """
        return [
            event
            async for event in service.stream_turn(
                request_id=str(uuid4()),
                session_id="session-id",
                question="Hello!",
                user=user,
            )
        ]

    task = asyncio.create_task(consume_turn())
    try:
        assert await asyncio.to_thread(memory.started.wait, 2)
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        memory.release.set()

    events = await task
    assert events[-1].event_type == "completed"


@pytest.mark.asyncio
async def test_chat_cancellation_propagates_during_session_read() -> None:
    """Propagate cancellation while a blocking history read runs in a thread.

    Releasing the fake worker ensures the test does not leave a waiting
    background thread behind.
    """
    memory = BlockingSessionStore()
    async_memory = AsyncSQLiteSessionStore(
        cast(SQLiteSessionStore, memory)
    )
    service = ChatService(
        InMemoryRetriever([]),
        async_memory,
        ToolRegistry(),
    )
    user = AuthenticatedUser(user_id="viewer", role=Role.VIEWER)

    async def consume_turn() -> None:
        """Start a chat turn and drain its activity stream.

        The coroutine remains cancellable while storage runs in a worker.
        """
        async for _event in service.stream_turn(
            request_id=str(uuid4()),
            session_id="session-id",
            question="Hello!",
            user=user,
        ):
            pass

    task = asyncio.create_task(consume_turn())
    try:
        assert await asyncio.to_thread(memory.started.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        memory.release.set()


@pytest.mark.asyncio
async def test_concurrent_sqlite_operations_keep_sessions_isolated(
    tmp_path: Path,
) -> None:
    """Keep parallel session writes isolated across operation connections.

    The store stays synchronous; the API-style caller offloads each
    operation so independent requests can proceed concurrently.

    Args:
        tmp_path: Pytest-managed location for a temporary database.
    """
    store = SQLiteSessionStore(str(tmp_path / "concurrent.sqlite3"))
    await asyncio.to_thread(store.initialize)
    owners = [f"user-{index}" for index in range(12)]
    sessions = await asyncio.gather(
        *(
            asyncio.to_thread(store.create_session, owner_id)
            for owner_id in owners
        )
    )

    await asyncio.gather(
        *(
            asyncio.to_thread(
                store.append_message,
                session.session_id,
                owner_id,
                "user",
                f"message-{index}",
            )
            for index, (owner_id, session) in enumerate(
                zip(owners, sessions, strict=True)
            )
        )
    )
    histories = await asyncio.gather(
        *(
            asyncio.to_thread(
                store.list_messages,
                session.session_id,
                owner_id,
            )
            for owner_id, session in zip(owners, sessions, strict=True)
        )
    )

    assert [history[0].content for history in histories if history] == [
        f"message-{index}" for index in range(len(owners))
    ]
