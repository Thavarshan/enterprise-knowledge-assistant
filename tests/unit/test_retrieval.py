"""Verify fixture access filtering and citation lineage checks.

The tests compare viewer and analyst result sets and ensure unsupported
citation markers fail validation without contacting a provider.
"""

import pytest

from enterprise_assistant.agents.graph import validate_citations
from enterprise_assistant.domain.models import (
    DocumentChunk,
    DocumentMetadata,
    SearchResult,
    SourceCitation,
)
from enterprise_assistant.retrieval.hybrid import reciprocal_rank_fusion
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
    identity = (citation.document_id, citation.chunk_id)
    assert validate_citations(
        f"Grounded answer {marker}", [citation], frozenset({identity})
    )
    assert not validate_citations(
        "Unsupported [fake#chunk]", [citation], frozenset({identity})
    )
    assert not validate_citations(
        f"Grounded answer {marker}",
        [citation],
        frozenset({("another-document", citation.chunk_id)}),
    )


def test_reciprocal_rank_fusion_keeps_complete_chunk_identities() -> None:
    """Keep equal chunk IDs separate when their parent documents differ.

    Document/chunk pairs, not chunk IDs alone, are stable retrieval and
    citation identities.
    """
    results = []
    for document_id in ("document-a", "document-b"):
        chunk = DocumentChunk(
            content=f"Synthetic content from {document_id}.",
            metadata=DocumentMetadata(
                document_id=document_id,
                chunk_id="shared-chunk",
                title=f"Synthetic {document_id}",
                department="payments",
                document_type="incident",
                access_level="viewer",
                created_date="2026-01-01",
                source=f"sample://{document_id}",
            ),
        )
        results.append(SearchResult(chunk=chunk, score=1.0, rank=1))

    fused = reciprocal_rank_fusion([results, list(reversed(results))])

    assert len(fused) == 2
    assert {
        result.chunk.metadata.document_id
        for result in fused
    } == {"document-a", "document-b"}
