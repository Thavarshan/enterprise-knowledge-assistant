"""Verify structured incident aggregation preserves facts and provenance.

The tests use fictional, validated source records and trusted Python
aggregation. They cover deduplication, dates, unknown causes, and citations.
"""

from datetime import date

import pytest
from pydantic import ValidationError

from enterprise_assistant.agents.graph import (
    render_incident_analysis,
    validate_citations,
)
from enterprise_assistant.domain.models import (
    DocumentChunk,
    DocumentMetadata,
    SearchResult,
)
from enterprise_assistant.tools.incident_analysis import (
    IncidentAnalysisTool,
    IncidentEvidence,
    evidence_from_results,
)


def _record(
    incident_id: str,
    chunk_id: str,
    *,
    category: str | None = "service_outage",
    cause: str | None = "retry_without_jitter",
    incident_date: date = date(2026, 1, 1),
) -> IncidentEvidence:
    """Create one fully attributed fictional incident record.

    Args:
        incident_id: Stable source incident identifier.
        chunk_id: Stable source passage identifier.
        category: Explicit incident classification, if present.
        cause: Explicit source cause, if present.
        incident_date: Source date used by analysis filtering.

    Returns:
        Validated synthetic incident evidence.
    """
    return IncidentEvidence(
        incident_id=incident_id,
        source_document_id=f"doc-{incident_id}",
        source_chunk_id=chunk_id,
        incident_date=incident_date,
        department="payments",
        incident_category=category,
        root_cause_category=cause,
    )


@pytest.mark.asyncio
async def test_analysis_counts_unique_incidents_and_inclusive_dates() -> None:
    """Count distinct incidents and apply inclusive source-date limits.

    Duplicate chunks count once, and the lower date boundary is included.
    """
    records = [
        _record("INC-A", "chunk-a1"),
        _record("INC-A", "chunk-a2"),
        _record("INC-B", "chunk-b"),
        _record("INC-C", "chunk-c", cause=None, category=None),
        _record(
            "INC-OLD",
            "chunk-old",
            incident_date=date(2025, 11, 14),
        ),
    ]

    result = await IncidentAnalysisTool().run(
        {
            "records": [record.model_dump(mode="json") for record in records],
            "date_from": date(2025, 11, 15),
            "date_to": date(2026, 11, 15),
        }
    )

    assert result.incidents_analyzed == 3
    assert result.unknown_root_cause_count == 1
    assert result.unclassified_incident_count == 1
    assert len(result.root_causes) == 1
    assert result.root_causes[0].incident_count == 2
    assert result.root_causes[0].percentage == 100
    assert {source.incident_id for source in result.sources} == {
        "INC-A",
        "INC-B",
        "INC-C",
    }


@pytest.mark.asyncio
async def test_conflicting_duplicate_causes_remain_unknown() -> None:
    """Do not assign a cause when duplicate source chunks conflict.

    Conflicting source classifications are grouped under unknown.
    """
    records = [
        _record("INC-A", "chunk-a1"),
        _record(
            "INC-A",
            "chunk-a2",
            cause="missing_idempotency_key",
        ),
    ]

    result = await IncidentAnalysisTool().run(
        {"records": [record.model_dump(mode="json") for record in records]}
    )

    assert result.incidents_analyzed == 1
    assert result.unknown_root_cause_count == 1
    assert result.root_causes == []
    assert len(result.sources) == 2


@pytest.mark.asyncio
async def test_empty_analysis_returns_a_well_formed_zero_result() -> None:
    """Return a zero-valued result for an empty record list.

    Empty input has no classified denominator or source references.
    """
    result = await IncidentAnalysisTool().run({"records": []})

    assert result.incidents_analyzed == 0
    assert result.root_causes == []
    assert result.sources == []


def test_incident_contract_rejects_extra_or_unknown_classification() -> None:
    """Reject unsupported fields and categories at the data boundary.

    The schema accepts only the explicitly maintained source vocabulary.
    """
    values = _record("INC-A", "chunk-a").model_dump(mode="json")

    with pytest.raises(ValidationError):
        IncidentEvidence.model_validate({**values, "tool": "delete"})
    with pytest.raises(ValidationError):
        IncidentEvidence.model_validate(
            {**values, "root_cause_category": "made_up_cause"}
        )


@pytest.mark.asyncio
async def test_analysis_citations_match_retrieved_identity() -> None:
    """Render citations that match complete document and chunk identities.

    The generated summary must cite source chunks returned this turn.
    """
    chunk = DocumentChunk(
        content="Synthetic retries saturated a payment queue.",
        metadata=DocumentMetadata(
            document_id="doc-INC-A",
            chunk_id="chunk-a",
            title="Synthetic incident INC-A",
            department="payments",
            document_type="incident_report",
            access_level="viewer",
            created_date="2026-01-01",
            source="sample://incidents/INC-A",
            incident_id="INC-A",
            incident_category="service_outage",
            root_cause_category="retry_without_jitter",
            severity="SEV-2",
            impact_summary="Payment requests were delayed.",
        ),
    )
    result = SearchResult(chunk=chunk, score=1.0, rank=1)
    evidence = evidence_from_results([result])
    parsed = await IncidentAnalysisTool().run(
        {"records": [record.model_dump(mode="json") for record in evidence]}
    )
    text, citations, grounded = render_incident_analysis(parsed, [result])
    identities = frozenset({("doc-INC-A", "chunk-a")})

    assert grounded
    assert "retry without jitter: 1 incident(s)" in text
    assert validate_citations(text, citations, identities)
    assert citations[0].document_id == "doc-INC-A"
