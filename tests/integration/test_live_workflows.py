"""Verify live workflows, Pinecone evidence, and informative LangSmith traces.

The opt-in suite uses only the checked-in synthetic corpus. It upserts those
records to the configured namespace, runs real OpenAI turns, and reads the
resulting LangSmith trees back before reporting a successful verification.
"""

import asyncio
import os
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from langsmith import Client
from scripts.verify_langsmith import _verify_remote_trace

from enterprise_assistant.chat.service import ChatService
from enterprise_assistant.config.settings import Settings, get_settings
from enterprise_assistant.domain.models import SearchResult
from enterprise_assistant.llm.providers import (
    MockModelProvider,
    OpenAIModelProvider,
    create_model_provider,
)
from enterprise_assistant.memory.models import ChatSession
from enterprise_assistant.memory.sqlite import SQLiteSessionStore
from enterprise_assistant.memory.sqlite_async import (
    AsyncSQLiteSessionStore,
)
from enterprise_assistant.observability.events import ActivityEvent
from enterprise_assistant.observability.langsmith import (
    create_langsmith_address,
    create_langsmith_client,
)
from enterprise_assistant.retrieval.hybrid import HybridRetriever
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever
from enterprise_assistant.retrieval.interfaces import Retriever
from enterprise_assistant.retrieval.pinecone import (
    PineconeConfig,
    PineconeRetriever,
)
from enterprise_assistant.security.authentication import AuthenticatedUser
from enterprise_assistant.security.authorization import Role
from enterprise_assistant.tools.registry import ToolRegistry


class FailingRetriever:
    """Raise a synthetic provider error for a redacted failure-span check.

    No result content is returned by this injected adapter.
    """

    async def search(
        self,
        query: str,
        *,
        allowed_access_levels: frozenset[str],
        department: str | None = None,
        document_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Fail without returning evidence or exposing the test sentinel.

        Args:
            query: User or research query.
            allowed_access_levels: Backend-derived search scope.
            department: Optional department constraint.
            document_type: Optional source type constraint.
            date_from: Inclusive lower date bound.
            date_to: Inclusive upper date bound.
            limit: Requested result count.

        Raises:
            RuntimeError: Always, to test the application's failure boundary.
        """
        del (
            query,
            allowed_access_levels,
            department,
            document_type,
            date_from,
            date_to,
            limit,
        )
        raise RuntimeError("RETRIEVAL_FAILURE_SENTINEL")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_openai_pinecone_research_analysis_and_tracing(
    tmp_path: Path,
) -> None:
    """Verify live routing, source analysis, tool security, and trace content.

    The test sends only synthetic assessment content to OpenAI, Pinecone, and
    LangSmith. Opt-in verification fails as BLOCKED when required credentials
    or remote trace-read permission are unavailable.

    Args:
        tmp_path: Pytest-managed location for a disposable SQLite database.
    """
    if os.environ.get("RUN_LIVE_WORKFLOW_TESTS") != "true":
        pytest.skip("Set RUN_LIVE_WORKFLOW_TESTS=true to opt in.")
    settings = get_settings()
    _require_live_configuration(settings)

    corpus = InMemoryRetriever.from_json(Path(settings.pinecone_documents_path))
    dense = PineconeRetriever(
        PineconeConfig(
            api_key=settings.pinecone_api_key,
            index_name=settings.pinecone_index_name,
            namespace=settings.pinecone_namespace,
            embedding_model=settings.pinecone_embedding_model,
            embedding_dimension=settings.pinecone_embedding_dimension,
            timeout_seconds=settings.pinecone_timeout_seconds,
        )
    )
    indexed_count = await dense.upsert_documents(corpus.chunks)
    assert indexed_count == len(corpus.chunks)

    trace_errors: list[str] = []

    def record_trace_error(error: Exception) -> None:
        """Retain only the class of any LangSmith submission error.

        Args:
            error: SDK callback error whose message may contain sensitive data.
        """
        trace_errors.append(type(error).__name__)

    client = create_langsmith_client(
        settings,
        tracing_error_callback=record_trace_error,
    )
    address = create_langsmith_address(settings)
    if client is None or address is None:
        pytest.fail("BLOCKED: LangSmith tracing client is unavailable.")

    provider = create_model_provider(settings)
    retriever: Retriever = HybridRetriever(dense, dense)
    memory = SQLiteSessionStore(str(tmp_path / "live-chat.sqlite3"))
    memory.initialize()
    async_memory = AsyncSQLiteSessionStore(memory)
    analyst_id = "live-analyst"
    viewer_id = "live-viewer"
    analyst_session = memory.create_session(analyst_id)
    viewer_session = memory.create_session(viewer_id)
    live_service = ChatService(
        retriever,
        async_memory,
        ToolRegistry(),
        langsmith_client=client,
        langsmith_address=address,
        model_provider=provider,
    )
    trace_specs: list[tuple[str, frozenset[str], dict[str, str]]] = []
    trace_visible_markers: dict[str, tuple[str, ...]] = {}
    forbidden_trace_spans: dict[str, frozenset[str]] = {}

    try:
        retrieval_id, retrieval_events = await _chat_turn(
            live_service,
            memory,
            analyst_session,
            "What happened in incident INC-2026-057?",
            Role.ANALYST,
        )
        trace_visible_markers[retrieval_id] = (
            "What happened in incident INC-2026-057?",
        )
        assert _route(retrieval_events) == "retrieval"
        retrieval_sources = _source_document_ids(retrieval_events)
        assert "incident-2026-057" in retrieval_sources
        assert _response_text(retrieval_events)
        assert _validation_passed(retrieval_events)
        trace_specs.append(
            (
                retrieval_id,
                frozenset(
                    {
                        "chat_request",
                        "supervisor",
                        "openai_supervisor",
                        "retrieval",
                        "knowledge_search",
                        "response",
                        "openai_response",
                        "validate",
                        "assistant_memory_append",
                    }
                ),
                {
                    "openai_supervisor": "supervisor",
                    "knowledge_search": "retrieval",
                    "openai_response": "response",
                    "assistant_memory_append": "chat_request",
                },
            )
        )

        research_id, research_events = await _chat_turn(
            live_service,
            memory,
            analyst_session,
            "Compare the symptoms and mitigations in incidents "
            "INC-2026-057 and INC-2026-041.",
            Role.ANALYST,
        )
        trace_visible_markers[research_id] = (
            "Compare the symptoms and mitigations in incidents "
            "INC-2026-057 and INC-2026-041.",
        )
        assert _route(research_events) == "research"
        research_status = _research_status(research_events)
        assert research_status["subtask_count"] >= 2
        assert research_status["search_calls"] >= 2
        assert {
            "incident-2026-057",
            "incident-2026-041",
        } <= _source_document_ids(research_events)
        assert _response_text(research_events)
        assert _validation_passed(research_events)
        trace_specs.append(
            (
                research_id,
                frozenset(
                    {
                        "chat_request",
                        "supervisor",
                        "openai_supervisor",
                        "research",
                        "openai_decomposition",
                        "knowledge_search",
                        "response",
                        "openai_response",
                        "validate",
                        "assistant_memory_append",
                    }
                ),
                {
                    "openai_supervisor": "supervisor",
                    "openai_decomposition": "research",
                    "knowledge_search": "research",
                    "openai_response": "response",
                    "assistant_memory_append": "chat_request",
                },
            )
        )

        analysis_id, analysis_events = await _chat_turn(
            live_service,
            memory,
            analyst_session,
            "Summarize payment outages during the last year and identify "
            "recurring root causes.",
            Role.ANALYST,
        )
        trace_visible_markers[analysis_id] = (
            "Summarize payment outages during the last year and identify "
            "recurring root causes.",
        )
        assert _route(analysis_events) == "research"
        analysis_status = _research_status(analysis_events)
        assert analysis_status["batch_count"] >= 1
        assert analysis_status["analyzed_incident_count"] > 0
        answer = _response_text(analysis_events)
        assert "2025-11-15 through 2026-11-15" in answer
        assert "retry without jitter" in answer
        assert _validation_passed(analysis_events)
        trace_specs.append(
            (
                analysis_id,
                frozenset(
                    {
                        "chat_request",
                        "supervisor",
                        "openai_supervisor",
                        "research",
                        "openai_decomposition",
                        "knowledge_search",
                        "incident_analysis",
                        "validate",
                        "assistant_memory_append",
                    }
                ),
                {
                    "openai_supervisor": "supervisor",
                    "openai_decomposition": "research",
                    "knowledge_search": "research",
                    "incident_analysis": "research",
                    "assistant_memory_append": "chat_request",
                },
            )
        )

        numeric_id, numeric_events = await _chat_turn(
            live_service,
            memory,
            analyst_session,
            "Calculate average of 10, 20, 30.",
            Role.ANALYST,
        )
        trace_visible_markers[numeric_id] = (
            "Calculate average of 10, 20, 30.",
        )
        assert _route(numeric_events) == "analysis"
        assert "20" in _response_text(numeric_events)
        assert _validation_passed(numeric_events)
        trace_specs.append(
            (
                numeric_id,
                frozenset(
                    {
                        "chat_request",
                        "supervisor",
                        "openai_supervisor",
                        "analysis",
                        "python_analysis",
                        "response",
                        "validate",
                        "assistant_memory_append",
                    }
                ),
                {
                    "openai_supervisor": "supervisor",
                    "python_analysis": "analysis",
                    "assistant_memory_append": "chat_request",
                },
            )
        )

        viewer_id_trace, viewer_events = await _chat_turn(
            live_service,
            memory,
            viewer_session,
            "Calculate average of 10, 20, 30.",
            Role.VIEWER,
        )
        trace_visible_markers[viewer_id_trace] = (
            "Calculate average of 10, 20, 30.",
        )
        assert _route(viewer_events) == "analysis"
        assert any(
            event.metadata.get("error_code") == "python_analysis_forbidden"
            for event in viewer_events
        )
        assert not any(
            event.event_type == "tool_start"
            and event.metadata.get("tool") == "python_analysis"
            for event in viewer_events
        )
        forbidden_trace_spans[viewer_id_trace] = frozenset({"python_analysis"})
        trace_specs.append(
            (
                viewer_id_trace,
                frozenset(
                    {
                        "chat_request",
                        "supervisor",
                        "openai_supervisor",
                        "analysis",
                        "response",
                        "validate",
                        "assistant_memory_append",
                    }
                ),
                {"openai_supervisor": "supervisor"},
            )
        )

        await _verify_retrieval_failure_trace(
            client,
            address,
            memory,
            trace_specs,
            trace_visible_markers,
        )
        await _verify_openai_failure_trace(
            settings,
            client,
            address,
            memory,
            trace_specs,
            trace_visible_markers,
        )

        client.flush(timeout=30)
        assert not trace_errors, "LangSmith trace submission reported errors."
        assert getattr(client.tracing_queue, "unfinished_tasks", 0) == 0
        verified: list[str] = []
        for request_id, expected, parent_spans in trace_specs:
            status, detail = _verify_remote_trace(
                client,
                verification_id=request_id,
                agent_id=settings.langsmith_agent_id,
                environment=settings.langsmith_agent_environment,
                visible_markers=trace_visible_markers.get(
                    request_id,
                    (),
                ),
                expected_spans=expected,
                expected_parent_spans=parent_spans,
                forbidden_spans=forbidden_trace_spans.get(
                    request_id,
                    frozenset(),
                ),
            )
            if status != "VERIFIED":
                pytest.fail(
                    f"BLOCKED: LangSmith trace {request_id} is {status}: "
                    f"{detail}"
                )
            verified.append(request_id)
        print("Verified LangSmith chat trace IDs:")
        for request_id in verified:
            print(request_id)
    finally:
        await provider.aclose()
        client.close(timeout=5)


def _require_live_configuration(settings: Settings) -> None:
    """Fail the opt-in verification clearly when a required service is absent.

    Args:
        settings: Environment-backed service configuration.

    Raises:
        pytest.fail.Exception: OpenAI, Pinecone, or LangSmith is not ready.
    """
    required = {
        "OPENAI_API_KEY": bool(settings.openai_api_key.strip()),
        "PINECONE_API_KEY": bool(settings.pinecone_api_key.strip()),
        "PINECONE_INDEX_NAME": bool(settings.pinecone_index_name.strip()),
        "PINECONE_NAMESPACE": bool(settings.pinecone_namespace.strip()),
        "LANGSMITH_TRACING": settings.langsmith_tracing,
        "LANGSMITH_API_KEY": bool(settings.langsmith_api_key.strip()),
        "LANGSMITH_AGENT_ID": bool(settings.langsmith_agent_id.strip()),
        "LANGSMITH_AGENT_ENVIRONMENT": bool(
            settings.langsmith_agent_environment.strip()
        ),
    }
    missing = [name for name, configured in required.items() if not configured]
    if settings.llm_provider != "openai" or settings.mock_mode:
        missing.extend(["LLM_PROVIDER=openai", "MOCK_MODE=false"])
    if missing:
        pytest.fail(
            "BLOCKED: live workflow verification requires " + ", ".join(missing)
        )


async def _chat_turn(
    service: ChatService,
    memory: SQLiteSessionStore,
    session: ChatSession,
    question: str,
    role: Role,
) -> tuple[str, list[ActivityEvent]]:
    """Persist a synthetic user message and run one real chat-service turn.

    Args:
        service: Graph-backed application chat service under test.
        memory: Temporary owner-scoped SQLite store.
        session: Test session receiving the synthetic turn.
        question: Synthetic message to route and answer.
        role: Backend role used for the test identity.

    Returns:
        Request trace ID and execution-accurate activity events.
    """
    await asyncio.to_thread(
        memory.append_message,
        session.session_id,
        session.owner_id,
        "user",
        question,
    )
    request_id = str(uuid4())
    user = AuthenticatedUser(user_id=session.owner_id, role=role)
    events = [
        event
        async for event in service.stream_turn(
            request_id=request_id,
            session_id=session.session_id,
            question=question,
            user=user,
        )
    ]
    return request_id, events


def _route(events: list[ActivityEvent]) -> str:
    """Read the route selected by the graph's supervisor activity event.

    Args:
        events: One completed chat's activity events.

    Returns:
        Selected workflow name.
    """
    for event in events:
        if (
            event.agent == "supervisor"
            and event.event_type == "agent_transition"
        ):
            return str(event.metadata["decision"])
    raise AssertionError("The supervisor route event was not emitted.")


def _source_document_ids(events: list[ActivityEvent]) -> set[str]:
    """Collect complete retrieved document IDs from activity metadata.

    Args:
        events: One completed chat's activity events.

    Returns:
        Document IDs announced by the retrieval activity event.
    """
    identities: set[str] = set()
    for event in events:
        sources = event.metadata.get("sources", [])
        if isinstance(sources, list):
            identities.update(
                str(source["document_id"])
                for source in sources
                if isinstance(source, dict) and "document_id" in source
            )
    return identities


def _response_text(events: list[ActivityEvent]) -> str:
    """Join validated answer chunks emitted after citation checking.

    Args:
        events: One completed chat's activity events.

    Returns:
        User-visible answer emitted by the graph.
    """
    return "".join(
        event.message
        for event in events
        if event.event_type == "response_chunk"
    )


def _validation_passed(events: list[ActivityEvent]) -> bool:
    """Return whether a validation event approved the final answer.

    Args:
        events: One completed chat's activity events.

    Returns:
        True when citation validation passed.
    """
    return any(
        event.event_type == "validation" and event.metadata.get("valid") is True
        for event in events
    )


def _research_status(events: list[ActivityEvent]) -> dict[str, Any]:
    """Extract safe counters from the Research completion event.

    Args:
        events: One completed research turn's activity events.

    Returns:
        Search, subtask, batch, and incident count metadata.
    """
    for event in events:
        if event.agent == "research" and event.event_type == "agent_transition":
            return event.metadata
    raise AssertionError("Research did not report its completion counters.")


async def _verify_retrieval_failure_trace(
    client: Client,
    address: Any,
    memory: SQLiteSessionStore,
    trace_specs: list[tuple[str, frozenset[str], dict[str, str]]],
    trace_visible_markers: dict[str, tuple[str, ...]],
) -> None:
    """Run a real graph retrieval failure and register its expected trace.

    Args:
        client: Configured, credential-scrubbing LangSmith client.
        address: Registered agent and environment destination.
        memory: Temporary SQLite store for the synthetic turn.
        trace_specs: Live trace IDs and expected hierarchy assertions.
        trace_visible_markers: Synthetic content that must appear in traces.
    """
    user_id = "retrieval-failure-analyst"
    session = memory.create_session(user_id)
    failing_service = ChatService(
        FailingRetriever(),
        AsyncSQLiteSessionStore(memory),
        ToolRegistry(),
        langsmith_client=client,
        langsmith_address=address,
        model_provider=MockModelProvider(),
    )
    request_id, events = await _chat_turn(
        failing_service,
        memory,
        session,
        "What does the payment retry policy require?",
        Role.ANALYST,
    )
    assert any(event.event_type == "failure" for event in events)
    trace_specs.append(
        (
            request_id,
            frozenset(
                {"chat_request", "supervisor", "retrieval", "knowledge_search"}
            ),
            {"knowledge_search": "retrieval"},
        )
    )
    trace_visible_markers[request_id] = (
        "What does the payment retry policy require?",
    )


async def _verify_openai_failure_trace(
    settings: Settings,
    client: Client,
    address: Any,
    memory: SQLiteSessionStore,
    trace_specs: list[tuple[str, frozenset[str], dict[str, str]]],
    trace_visible_markers: dict[str, tuple[str, ...]],
) -> None:
    """Cause one invalid-model response and record the sanitized failure tree.

    Args:
        settings: Live OpenAI credentials and timeout configuration.
        client: Configured, credential-scrubbing LangSmith client.
        address: Registered agent and environment destination.
        memory: Temporary SQLite store for the synthetic turn.
        trace_specs: Live trace IDs and expected hierarchy assertions.
        trace_visible_markers: Synthetic content that must appear in traces.
    """
    user_id = "provider-failure-analyst"
    session = memory.create_session(user_id)
    sentinel_model = "LANGSMITH_MODEL_SENTINEL_DO_NOT_EXPORT"
    failing_provider = OpenAIModelProvider(
        settings.openai_api_key,
        sentinel_model,
        settings.llm_timeout_seconds,
    )
    failing_service = ChatService(
        InMemoryRetriever.from_json(Path(settings.pinecone_documents_path)),
        AsyncSQLiteSessionStore(memory),
        ToolRegistry(),
        langsmith_client=client,
        langsmith_address=address,
        model_provider=failing_provider,
    )
    try:
        request_id, events = await _chat_turn(
            failing_service,
            memory,
            session,
            "What does the payment retry policy require?",
            Role.ANALYST,
        )
        assert any(event.event_type == "failure" for event in events)
    finally:
        await failing_provider.aclose()
    trace_specs.append(
        (
            request_id,
            frozenset({"chat_request", "supervisor", "openai_supervisor"}),
            {"openai_supervisor": "supervisor"},
        )
    )
    trace_visible_markers[request_id] = (
        "What does the payment retry policy require?",
    )
