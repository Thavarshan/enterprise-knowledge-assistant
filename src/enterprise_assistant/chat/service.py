"""Adapt an authenticated chat turn to LangGraph and session persistence.

The service creates initial graph state from server-resolved identity,
streams node-produced events, captures the validated response, and persists
it only after graph completion. Graph and persistence failures become safe
activity events; exception details are limited to structured logs.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import nullcontext
from typing import Any
from uuid import UUID, uuid4

from langsmith import AgentAddress, Client, trace, traceable

from enterprise_assistant.agents.graph import build_graph
from enterprise_assistant.agents.state import AgentState
from enterprise_assistant.llm.contracts import ModelProvider
from enterprise_assistant.llm.providers import MockModelProvider
from enterprise_assistant.memory.interfaces import SessionStore
from enterprise_assistant.observability.events import ActivityEvent
from enterprise_assistant.retrieval.interfaces import Retriever
from enterprise_assistant.security.authentication import AuthenticatedUser
from enterprise_assistant.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@traceable(
    name="assistant_memory_append",
    run_type="tool",
    metadata={"tool_name": "session_memory_append"},
)
def _append_assistant_message(
    memory: SessionStore,
    session_id: str,
    user_id: str,
    response_text: str,
) -> None:
    """Persist the assistant answer as a child operation in the chat trace.

    The LangSmith client hides inputs and outputs, so the message text and
    memory adapter details are not exported.

    Args:
        memory: Session store configured by the application.
        session_id: Owner-scoped conversation identifier.
        user_id: Authenticated account identifier.
        response_text: Completed assistant answer to persist.
    """
    memory.append_message(
        session_id,
        user_id,
        "assistant",
        response_text,
    )


class ChatService:
    """Run the graph for a turn and persist the final assistant message.

    The service translates LangGraph node updates into validated activity
    events. It stores an assistant response only after graph completion;
    failures are logged by type and returned as generic events.

    Attributes:
        memory: Synchronous session store used for assistant persistence.
        graph: Compiled LangGraph workflow built from injected adapters.

    Notes:
        No checkpointer is configured, so a thread ID in run metadata does
        not make graph state durable.
    """

    def __init__(
        self,
        retriever: Retriever,
        memory: SessionStore,
        tool_registry: ToolRegistry,
        langsmith_client: Client | None = None,
        langsmith_address: AgentAddress | None = None,
        model_provider: ModelProvider | None = None,
    ) -> None:
        """Build a graph around injected retrieval and tool policy.

        Args:
            retriever: Adapter used by the knowledge-search tool.
            memory: Session store used after a successful graph run.
            tool_registry: Role policy applied before tool handler dispatch.
            langsmith_client: Optional redacting client for graph traces.
            langsmith_address: Agent and environment for graph traces.
            model_provider: Structured model adapter for agent decisions.
        """
        self.memory = memory
        self.model_provider = model_provider or MockModelProvider()
        self.graph: Any = build_graph(
            retriever,
            tool_registry,
            self.model_provider,
        )
        self.langsmith_client = langsmith_client
        self.langsmith_address = langsmith_address

    async def stream_turn(
        self,
        *,
        request_id: str,
        session_id: str,
        question: str,
        user: AuthenticatedUser,
    ) -> AsyncIterator[ActivityEvent]:
        """Stream a graph run and persist its final answer.

        Initial identity and role come from the authenticated API user.
        Node updates are converted to ActivityEvent objects while response
        text and citation count are collected. Graph failures yield a
        generic failure event and stop; assistant persistence errors also
        yield a failure event. The user message was persisted by the route.

        Args:
            request_id: Correlation identifier assigned by middleware.
            session_id: Owner-scoped conversation thread identifier.
            question: Validated message passed to the graph.
            user: Authenticated identity and server-assigned role.

        Yields:
            Typed graph activity, persistence, completion, or failure
            events.

        Side Effects:
            Appends an assistant message after graph success. Events and
            provider exception details are not saved to session history.

        Notes:
            The graph run uses LangGraph update streaming. The configured
            thread ID is metadata only because no checkpointer is supplied.
        """
        messages = self.memory.list_messages(session_id, user.user_id) or []
        if (
            messages
            and messages[-1].role == "user"
            and messages[-1].content == question
        ):
            messages = messages[:-1]
        state: AgentState = {
            "request_id": request_id,
            "session_id": session_id,
            "user_id": user.user_id,
            "role": user.role.value,
            "question": question,
            "history": messages[-12:],
            "events": [],
        }
        response_text = ""
        citation_count = 0
        phase = "graph"
        try:
            trace_id = UUID(request_id)
        except ValueError:
            trace_id = uuid4()

        trace_context = (
            trace(
                name="chat_request",
                run_type="chain",
                inputs={
                    "request_id": request_id,
                    "session_id": session_id,
                    "question": question,
                },
                address=self.langsmith_address,
                client=self.langsmith_client,
                run_id=trace_id,
                metadata={
                    "agent_id": (
                        self.langsmith_address["id"]
                        if self.langsmith_address
                        else ""
                    ),
                    "agent_environment": (
                        self.langsmith_address["environment"]
                        if self.langsmith_address
                        else ""
                    ),
                    "agent_name": "Enterprise Knowledge Assistant",
                    "request_id": request_id,
                    "session_id": session_id,
                    "status": "running",
                    "workflow": "chat",
                },
            )
            if self.langsmith_client is not None
            and self.langsmith_address is not None
            else nullcontext(None)
        )
        try:
            with trace_context as trace_run:
                try:
                    async for update in self.graph.astream(
                        state,
                        stream_mode="updates",
                        config={
                            "configurable": {"thread_id": session_id},
                            "metadata": {
                                "request_id": request_id,
                                "session_id": session_id,
                            },
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
                    phase = "persistence"
                    _append_assistant_message(
                        self.memory,
                        session_id,
                        user.user_id,
                        response_text,
                    )
                    if trace_run is not None:
                        trace_run.metadata["status"] = "success"
                except Exception:
                    if trace_run is not None:
                        trace_run.metadata["status"] = "failure"
                    raise
        except Exception as exc:
            if phase == "persistence":
                logger.error(
                    "Assistant turn persistence failed",
                    extra={"request_id": request_id,
                           "error_type": type(exc).__name__},
                )
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
            logger.error(
                "Agent graph failed",
                extra={"request_id": request_id,
                       "error_type": type(exc).__name__},
            )
            yield ActivityEvent(
                event_type="failure",
                request_id=request_id,
                session_id=session_id,
                agent="assistant",
                node="graph",
                message=(
                    "The assistant could not complete this request. "
                    "Please try again."
                ),
                metadata={"error_code": "agent_execution_failed"},
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
