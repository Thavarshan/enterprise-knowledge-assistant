"""Verify fixture access filtering and citation lineage checks.

The tests compare viewer and analyst result sets and ensure unsupported
citation markers fail validation without contacting a provider.
"""

from datetime import date
from pathlib import Path

import pytest

from enterprise_assistant.agents.graph import validate_citations
from enterprise_assistant.domain.models import (
    DocumentChunk,
    DocumentMetadata,
    SearchResult,
    SourceCitation,
)
from enterprise_assistant.retrieval.filters import filters_for_question
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


def test_last_year_filter_uses_injected_rolling_date_window() -> None:
    """Interpret last year as a rolling inclusive anniversary window.

    The injected date keeps boundary behavior repeatable in tests.
    """
    filters = filters_for_question(
        "Summarize payment outages during the last year",
        today=date(2026, 11, 15),
    )

    assert filters.document_type == "incident_report"
    assert filters.date_from == date(2025, 11, 15)
    assert filters.date_to == date(2026, 11, 15)


def test_known_department_terms_narrow_filters() -> None:
    """Resolve department names from user text without changing role scope.

    A department constraint narrows metadata search independently of RBAC.
    """
    payments = filters_for_question(
        "Summarize payment outages during the last year",
        today=date(2026, 11, 15),
    )
    platform = filters_for_question(
        "Find platform engineering runbooks",
        today=date(2026, 11, 15),
    )

    assert payments.department == "payments"
    assert platform.department == "platform-engineering"


def test_last_year_filter_clamps_leap_day_safely() -> None:
    """Clamp a prior-year leap day to a valid calendar date.

    February 29 maps to February 28 when the previous year is not a leap year.
    """
    filters = filters_for_question(
        "Incidents from the past year",
        today=date(2024, 2, 29),
    )

    assert filters.date_from == date(2023, 2, 28)
    assert filters.date_to == date(2024, 2, 29)


@pytest.mark.asyncio
async def test_in_memory_retrieval_applies_type_and_date_filters() -> None:
    """Filter older incidents before returning evidence chunks.

    Document type and date constraints are applied alongside access policy.
    """
    retriever = InMemoryRetriever.from_json(
        Path("data/samples/incident_corpus.json")
    )

    results = await retriever.search(
        "Synthetic payment incident outage",
        allowed_access_levels=frozenset({"viewer", "analyst"}),
        document_type="incident_report",
        date_from=date(2025, 11, 15),
        date_to=date(2026, 11, 15),
        limit=20,
    )

    assert results
    assert all(
        result.chunk.metadata.document_type == "incident_report"
        and date(2025, 11, 15)
        <= result.chunk.metadata.created_date
        <= date(2026, 11, 15)
        for result in results
    )
