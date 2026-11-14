"""Verify model provider contracts and the deterministic mock workflow.

These unit tests use no network calls. They prove that model outputs are
validated, complete citation identities are enforced, and injected provider
decisions reach the graph without controlling role policy.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from enterprise_assistant.agents.graph import (
    build_graph,
    render_grounded_answer,
)
from enterprise_assistant.agents.state import AgentState
from enterprise_assistant.domain.models import (
    DocumentChunk,
    DocumentMetadata,
    SearchResult,
)
from enterprise_assistant.llm.contracts import (
    CitationIdentity,
    GroundedAnswer,
    GroundedClaim,
    ModelProvider,
    SupervisorDecision,
)
from enterprise_assistant.llm.providers import (
    LLMProviderError,
    MockModelProvider,
    OpenAIModelProvider,
)
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever
from enterprise_assistant.security.authorization import Role
from enterprise_assistant.tools.registry import ToolRegistry


def _sample_result() -> SearchResult:
    """Create a synthetic result with stable complete attribution.

    Returns:
        One result containing no customer or production data.
    """
    chunk = DocumentChunk(
        content="Gateway retries caused duplicate payment attempts.",
        metadata=DocumentMetadata(
            document_id="incident-gateway-01",
            chunk_id="incident-gateway-01-001",
            title="Gateway retry incident",
            department="payments",
            document_type="incident",
            access_level="viewer",
            created_date="2026-01-01",
            source="sample://incidents/gateway-01",
        ),
    )
    return SearchResult(chunk=chunk, score=1.0, rank=1)


@pytest.mark.asyncio
async def test_mock_provider_returns_deterministic_structured_outputs() -> None:
    """Verify mock routing, grounded claims, and research planning.

    The local mock contract remains repeatable and independent of provider
    credentials.
    """
    provider = MockModelProvider()
    result = _sample_result()

    for prompt in (
        "Hello!",
        "Thanks.",
        "What can you do?",
        "Goodbye.",
    ):
        assert (
            await provider.classify_intent(prompt)
        ).route == "small_talk"
    assert (await provider.classify_intent("Compare incidents")).route == (
        "research"
    )
    assert (
        await provider.classify_intent("What does the payment runbook say?")
    ).route == "retrieval"
    assert (
        await provider.classify_intent("Calculate sum of 10, 20")
    ).route == "analysis"
    answer = await provider.generate_answer("Explain the incident", [result])
    assert answer.claims[0].citations == [
        CitationIdentity(
            document_id="incident-gateway-01",
            chunk_id="incident-gateway-01-001",
        )
    ]
    plan = await provider.decompose_question("Investigate outage incidents")
    assert len(plan.subtasks) > 1


def test_grounded_renderer_rejects_partial_identity_matches() -> None:
    """Verify both document and chunk IDs must match.

    Equal chunk IDs from different documents must not share citation
    authority.
    """
    result = _sample_result()
    answer = GroundedAnswer(
        claims=[
            GroundedClaim(
                text="The source describes a retry failure.",
                citations=[
                    CitationIdentity(
                        document_id="different-document",
                        chunk_id=result.chunk.metadata.chunk_id,
                    )
                ],
            )
        ]
    )

    text, citations, grounded = render_grounded_answer(answer, [result])

    assert "retry failure" in text
    assert citations == []
    assert not grounded


@pytest.mark.asyncio
async def test_graph_uses_injected_model_decision_and_grounded_answer() -> None:
    """Verify provider routing and answer generation are awaited by graph.

    The fixed provider chooses direct retrieval for a question that contains
    the keyword policy's research term, proving the injected model decision
    controls workflow selection while the authenticated role stays in state.
    """
    provider = AsyncMock(spec=ModelProvider)
    provider.classify_intent.return_value = SupervisorDecision(
        route="retrieval"
    )
    result = _sample_result()
    provider.generate_answer.return_value = GroundedAnswer(
        claims=[
            GroundedClaim(
                text="Retries caused duplicates.",
                citations=[
                    CitationIdentity(
                        document_id=result.chunk.metadata.document_id,
                        chunk_id=result.chunk.metadata.chunk_id,
                    )
                ],
            )
        ]
    )
    retriever = InMemoryRetriever([result.chunk])
    graph = build_graph(
        retriever,
        ToolRegistry(),
        provider,
    )
    state: AgentState = {
        "request_id": "provider-test",
        "session_id": "session-test",
        "user_id": "viewer",
        "role": Role.VIEWER.value,
        "question": "Compare retry behavior",
        "events": [],
    }

    updates = [
        update async for update in graph.astream(state, stream_mode="updates")
    ]
    node_names = [node for update in updates for node in update]

    assert node_names == ["supervisor", "retrieval", "response", "validate"]
    provider.classify_intent.assert_awaited_once()
    provider.generate_answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_openai_provider_timeout_is_sanitized() -> None:
    """Verify a stalled OpenAI call becomes a safe provider error.

    The mocked SDK operation exceeds the configured timeout without
    contacting the provider or leaking exception details.
    """
    provider = OpenAIModelProvider(
        api_key="synthetic-key",
        model="synthetic-model",
        timeout_seconds=1,
    )

    async def slow_parse(**kwargs):
        """Simulate an unresponsive provider SDK call.

        Args:
            kwargs: SDK request fields unused by the fake operation.
        """
        del kwargs
        await asyncio.sleep(1.1)

    provider._client.responses.parse = AsyncMock(side_effect=slow_parse)
    try:
        with pytest.raises(LLMProviderError) as error:
            await provider.classify_intent("payment timeout")
        assert "synthetic-key" not in str(error.value)
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_openai_provider_preserves_caller_cancellation() -> None:
    """Verify request cancellation propagates through the provider adapter.

    The SDK call is mocked and signaled before cancellation so the test
    checks the active request path rather than a task that never started.
    """
    provider = OpenAIModelProvider(
        api_key="synthetic-key",
        model="synthetic-model",
        timeout_seconds=5,
    )
    started = asyncio.Event()

    async def wait_for_cancellation(**kwargs):
        """Wait until the caller cancels this mocked SDK request.

        Args:
            kwargs: SDK request fields unused by the fake operation.
        """
        del kwargs
        started.set()
        await asyncio.Event().wait()

    provider._client.responses.parse = AsyncMock(
        side_effect=wait_for_cancellation
    )
    task = asyncio.create_task(
        provider.classify_intent("payment timeout")
    )
    try:
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        if not task.done():
            task.cancel()
        await provider.aclose()
