"""Verify model provider contracts and the deterministic mock workflow.

These unit tests use no network calls. They prove that model outputs are
validated, complete citation identities are enforced, and injected provider
decisions reach the graph without controlling role policy.
"""

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
from enterprise_assistant.llm.providers import MockModelProvider
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

    assert (await provider.classify_intent("Compare incidents")).route == (
        "research"
    )
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
