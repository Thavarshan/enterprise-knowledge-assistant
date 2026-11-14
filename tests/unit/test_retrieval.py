"""Fixture retrieval and citation lineage contracts."""

import pytest

from enterprise_assistant.agents.graph import validate_citations
from enterprise_assistant.domain.models import SourceCitation
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever


@pytest.mark.asyncio
async def test_retrieval_applies_access_filter_before_returning_chunks() -> None:
    retriever = InMemoryRetriever.from_json()
    viewer_results = await retriever.search(
        "gateway payment timeout",
        allowed_access_levels=frozenset({"viewer"}),
    )
    analyst_results = await retriever.search(
        "gateway payment timeout",
        allowed_access_levels=frozenset({"viewer", "analyst"}),
    )
    assert viewer_results
    assert all(result.chunk.metadata.access_level == "viewer" for result in viewer_results)
    assert len(analyst_results) > len(viewer_results)


def test_citations_must_reference_retrieved_chunks() -> None:
    citation = SourceCitation(
        document_id="doc-runbook-gateway-timeout",
        chunk_id="doc-runbook-gateway-timeout-001",
        title="Gateway Timeout Response Runbook",
        source="sample://payments/runbooks/gateway-timeout",
    )
    marker = f"[{citation.document_id}#{citation.chunk_id}]"
    assert validate_citations(
        f"Grounded answer {marker}", [citation], frozenset({citation.chunk_id})
    )
    assert not validate_citations(
        "Unsupported [fake#chunk]", [citation], frozenset({citation.chunk_id})
    )
    assert not validate_citations(f"Grounded answer {marker}", [citation], frozenset())
