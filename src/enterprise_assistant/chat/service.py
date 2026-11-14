"""Translate LangGraph node updates into safe activity events and persisted turns."""

import logging
from collections.abc import AsyncIterator
from typing import Any

from enterprise_assistant.agents.graph import build_graph
from enterprise_assistant.agents.state import AgentState
from enterprise_assistant.memory.interfaces import SessionStore
from enterprise_assistant.observability.events import ActivityEvent
from enterprise_assistant.retrieval.interfaces import Retriever
from enterprise_assistant.security.authentication import AuthenticatedUser
from enterprise_assistant.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        retriever: Retriever,
        memory: SessionStore,
        tool_registry: ToolRegistry,
    ) -> None:
        self.memory = memory
        self.graph: Any = build_graph(retriever, tool_registry)

    async def stream_turn(
        self,
        *,
        request_id: str,
        session_id: str,
        question: str,
        user: AuthenticatedUser,
    ) -> AsyncIterator[ActivityEvent]:
        state: AgentState = {
            "request_id": request_id,
            "session_id": session_id,
            "user_id": user.user_id,
            "role": user.role.value,
            "question": question,
            "events": [],
        }
        response_text = ""
        citation_count = 0
        try:
            async for update in self.graph.astream(
                state,
                stream_mode="updates",
                config={
                    "configurable": {"thread_id": session_id},
                    "metadata": {"request_id": request_id, "session_id": session_id},
                },
            ):
                for node_update in update.values():
                    for raw_event in node_update.get("events", []):
                        event = ActivityEvent.model_validate(raw_event)
                        yield event
                    if "response" in node_update:
                        response_text = str(node_update["response"])
                    if "citations" in node_update:
                        citation_count = len(node_update["citations"])
        except Exception as exc:
            logger.error(
                "Agent graph failed",
                extra={"request_id": request_id, "error_type": type(exc).__name__},
            )
            yield ActivityEvent(
                event_type="failure",
                request_id=request_id,
                session_id=session_id,
                agent="assistant",
                node="graph",
                message="The assistant could not complete this request. Please try again.",
                metadata={"error_code": "agent_execution_failed"},
            )
            return

        try:
            self.memory.append_message(session_id, user.user_id, "assistant", response_text)
        except LookupError:
            logger.error("Assistant turn persistence failed", extra={"request_id": request_id})
            yield ActivityEvent(
                event_type="failure",
                request_id=request_id,
                session_id=session_id,
                agent="memory",
                node="persist",
                message="The response could not be saved to this session.",
                metadata={"error_code": "session_persistence_failed"},
            )
            return

        yield ActivityEvent(
            event_type="memory_update",
            request_id=request_id,
            session_id=session_id,
            agent="memory",
            node="persist",
            message="Saved the assistant turn to this session.",
        )
        yield ActivityEvent(
            event_type="completed",
            request_id=request_id,
            session_id=session_id,
            agent="assistant",
            node="complete",
            message="Assistant turn completed.",
            metadata={"citation_count": citation_count},
        )
