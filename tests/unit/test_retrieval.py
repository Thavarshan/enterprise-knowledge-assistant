"""Verify fixture access filtering and citation lineage checks.

The tests compare viewer and analyst result sets and ensure unsupported
citation markers fail validation without contacting a provider.
"""

import pytest

from enterprise_assistant.agents.graph import validate_citations
from enterprise_assistant.domain.models import SourceCitation
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever


@pytest.mark.asyncio
async def test_retrieval_applies_access_filter_before_returning_chunks(
) -> None:
    """Verify role-derived access filtering precedes fixture result exposure.

    Viewer results contain only viewer-labeled chunks, while an analyst can
    also retrieve analyst-labeled chunks.
    """
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
    assert all(result.chunk.metadata.access_level ==
               "viewer" for result in viewer_results)
    assert len(analyst_results) > len(viewer_results)


def test_citations_must_reference_retrieved_chunks() -> None:
    """Verify citation markers match the current retrieval evidence set.

    Valid markers pass, invented markers fail, and citations fail when no
    corresponding retrieved chunk ID is supplied.
    """
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
    assert not validate_citations(
        f"Grounded answer {marker}", [citation], frozenset())
