"""Run deterministic, fixture-grounded chat in the Cloudflare Worker.

Cloudflare's Pyodide package index does not provide a compatible
``ormsgpack`` wheel required by LangGraph. The free-tier Worker therefore
uses this small extractive service while the full LangGraph workflow remains
available to the local Python application.
"""

import logging
from collections.abc import AsyncIterator

from enterprise_assistant.memory.interfaces import SessionStore
from enterprise_assistant.observability.events import ActivityEvent
from enterprise_assistant.retrieval.interfaces import Retriever
from enterprise_assistant.security.authentication import AuthenticatedUser
from enterprise_assistant.security.authorization import allowed_access_levels

logger = logging.getLogger(__name__)


class WorkersMockChatService:
    """Return deterministic answers from role-filtered fixture evidence.

    This lightweight service keeps the Cloudflare demo within its free plan.
    """

    def __init__(self, retriever: Retriever, memory: SessionStore) -> None:
        """Store fixture search and owner-scoped persistence adapters.

        Args:
            retriever: Role-filtered in-memory knowledge search adapter.
            memory: Session store that persists messages by user ownership.
        """
        self.retriever = retriever
        self.memory = memory

    async def stream_turn(
        self,
        *,
        request_id: str,
        session_id: str,
        question: str,
        user: AuthenticatedUser,
    ) -> AsyncIterator[ActivityEvent]:
        """Search authorized fixtures, stream the answer, and save it.

        Args:
            request_id: Request correlation ID for each emitted event.
            session_id: Existing conversation session to continue.
            question: User's latest question.
            user: Authenticated user whose role filters retrieval access.

        Yields:
            Retrieval, response, and completion events for this turn.
        """
        yield ActivityEvent(
            event_type="agent_start",
            request_id=request_id,
            session_id=session_id,
            agent="Viridian",
            node="search",
            message="Searching the approved knowledge sources.",
        )
        try:
            results = await self.retriever.search(
                question,
                allowed_access_levels=allowed_access_levels(user.role),
                limit=3,
            )
            references = [
                {
                    "document_id": result.chunk.metadata.document_id,
                    "chunk_id": result.chunk.metadata.chunk_id,
                    "title": result.chunk.metadata.title,
                    "source": result.chunk.metadata.source,
                }
                for result in results
            ]
            yield ActivityEvent(
                event_type="retrieval",
                request_id=request_id,
                session_id=session_id,
                agent="Knowledge",
                node="fixtures",
                message=f"Found {len(results)} relevant source(s).",
                metadata={"citations": references},
            )
            if results:
                answer = "\n\n".join(
                    f"{result.chunk.content[:1200]}\n\n"
                    f"Source: {result.chunk.metadata.title} "
                    f"({result.chunk.metadata.source})"
                    for result in results[:2]
                )
            else:
                answer = (
                    "I couldn't find a matching source in the demo "
                    "knowledge base. Try asking about payment incidents, "
                    "retries, webhooks, or recovery steps."
                )
            yield ActivityEvent(
                event_type="response_chunk",
                request_id=request_id,
                session_id=session_id,
                agent="Viridian",
                node="response",
                message=answer,
                metadata={"citations": references},
            )
            await self.memory.append_message(
                session_id,
                user.user_id,
                "assistant",
                answer,
            )
        except Exception as exc:
            logger.error(
                "Cloudflare mock chat failed",
                extra={
                    "request_id": request_id,
                    "error_type": type(exc).__name__,
                },
            )
            yield ActivityEvent(
                event_type="failure",
                request_id=request_id,
                session_id=session_id,
                agent="Viridian",
                node="chat",
                message="The assistant could not complete this request.",
                metadata={"error_code": "chat_failed"},
            )
            return
        yield ActivityEvent(
            event_type="memory_update",
            request_id=request_id,
            session_id=session_id,
            agent="Memory",
            node="persist",
            message="Saved the assistant answer to this session.",
        )
        yield ActivityEvent(
            event_type="completed",
            request_id=request_id,
            session_id=session_id,
            agent="Viridian",
            node="complete",
            message="Assistant turn completed.",
            metadata={"citation_count": len(results)},
        )
