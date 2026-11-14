"""Analyze retrieved incident metadata with trusted Python operations.

Only structured fields attached to authorized source chunks enter this tool.
It never infers a cause from prose or executes model-generated code. Duplicate
chunks count as one incident, conflicting cause labels remain unclassified,
and all findings retain complete document/chunk identities.
"""

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from langsmith import traceable
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from enterprise_assistant.domain.models import (
    IncidentCategory,
    IncidentSeverity,
    RootCauseCategory,
    SearchResult,
)

_AGGREGATION_REQUEST = re.compile(
    r"\b(?:recurring|frequency|frequencies|breakdown|distribution|"
    r"percentage|percentages|how many|count|trend|trends)\b",
    re.IGNORECASE,
)
_INCIDENT_REQUEST = re.compile(
    r"\b(?:incident|incidents|outage|outages)\b", re.IGNORECASE
)


def is_incident_analysis_question(question: str) -> bool:
    """Recognize explicit aggregate requests over incident records.

    Args:
        question: Original user request selected for research.

    Returns:
        True when the request asks for counts or recurring incident patterns.
    """
    return bool(
        _AGGREGATION_REQUEST.search(question)
        and _INCIDENT_REQUEST.search(question)
    )


class IncidentEvidence(BaseModel):
    """Validate structured facts and provenance from one retrieved chunk.

    Attributes:
        incident_id: Source incident ID or stable document ID fallback.
        source_document_id: Complete parent document identity.
        source_chunk_id: Complete evidence chunk identity.
        incident_date: Source incident date used for scoped analysis.
        department: Source department label.
        incident_category: Explicit source category, when available.
        root_cause_category: Explicit source root cause, when available.
        severity: Explicit source severity, when available.
        impact_summary: Explicit source impact statement, when available.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    incident_id: str = Field(min_length=1, max_length=80)
    source_document_id: str = Field(min_length=1, max_length=128)
    source_chunk_id: str = Field(min_length=1, max_length=128)
    incident_date: date
    department: str = Field(min_length=1, max_length=80)
    incident_category: IncidentCategory | None = None
    root_cause_category: RootCauseCategory | None = None
    severity: IncidentSeverity | None = None
    impact_summary: str | None = Field(default=None, max_length=500)


class IncidentSourceReference(BaseModel):
    """Identify one source chunk supporting an incident finding.

    Attributes:
        incident_id: Source incident ID or stable document ID fallback.
        document_id: Complete parent document identity.
        chunk_id: Complete evidence chunk identity.
        incident_date: Source date attached to the incident.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    incident_id: str
    document_id: str
    chunk_id: str
    incident_date: date


class RootCauseFrequency(BaseModel):
    """Report the verified frequency and provenance of one cause category.

    Attributes:
        category: Explicit root-cause label from source metadata.
        incident_count: Number of distinct incidents with this cause.
        percentage: Share of classified incidents, rounded to two decimals.
        sources: Retrieved chunks supporting these source labels.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: RootCauseCategory
    incident_count: int = Field(ge=1)
    percentage: FiniteFloat = Field(ge=0, le=100)
    sources: list[IncidentSourceReference] = Field(min_length=1)


class IncidentAnalysisRequest(BaseModel):
    """Validate retrieved incident facts and an optional inclusive date range.

    Attributes:
        records: Authorized source facts to deduplicate and aggregate.
        date_from: Optional inclusive lower incident-date boundary.
        date_to: Optional inclusive upper incident-date boundary.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    records: list[IncidentEvidence] = Field(max_length=100)
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "IncidentAnalysisRequest":
        """Reject reversed date boundaries before processing records.

        Returns:
            The validated request.

        Raises:
            ValueError: The lower boundary is after the upper boundary.
        """
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("date_from must not be after date_to")
        return self


class IncidentAnalysisResult(BaseModel):
    """Return deduplicated counts, categories, and complete source references.

    Attributes:
        incidents_analyzed: Distinct incidents included after date filtering.
        date_from: Effective inclusive lower boundary, if requested.
        date_to: Effective inclusive upper boundary, if requested.
        root_causes: Counts and sources for explicitly classified incidents.
        unknown_root_cause_count: Incidents with missing or conflicting causes.
        unclassified_incident_count: Incidents missing an explicit category.
        sources: All distinct source chunks included in the analysis.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    incidents_analyzed: int = Field(ge=0, le=100)
    date_from: date | None = None
    date_to: date | None = None
    root_causes: list[RootCauseFrequency]
    unknown_root_cause_count: int = Field(ge=0, le=100)
    unclassified_incident_count: int = Field(ge=0, le=100)
    sources: list[IncidentSourceReference]


def evidence_from_results(
    results: Sequence[SearchResult],
) -> list[IncidentEvidence]:
    """Copy only structured incident fields from authorized results.

    Args:
        results: Chunks already filtered by server-side access policy.

    Returns:
        Validated incident records for incident-report chunks only.
    """
    records: list[IncidentEvidence] = []
    for result in results:
        metadata = result.chunk.metadata
        if metadata.document_type != "incident_report":
            continue
        records.append(
            IncidentEvidence(
                incident_id=metadata.incident_id or metadata.document_id,
                source_document_id=metadata.document_id,
                source_chunk_id=metadata.chunk_id,
                incident_date=metadata.created_date,
                department=metadata.department,
                incident_category=metadata.incident_category,
                root_cause_category=metadata.root_cause_category,
                severity=metadata.severity,
                impact_summary=metadata.impact_summary,
            )
        )
    return records


class IncidentAnalysisTool:
    """Run deterministic category counts over validated retrieved records.

    Role authorization is enforced by ``ToolRegistry`` before this handler is
    invoked. This class accepts no access labels and cannot fetch documents.
    """

    @traceable(
        name="incident_analysis",
        run_type="tool",
        metadata={"tool_name": "incident_analysis"},
    )
    async def run(
        self,
        arguments: Mapping[str, Any],
    ) -> IncidentAnalysisResult:
        """Filter, deduplicate, and aggregate source-classified incidents.

        Args:
            arguments: Records and date bounds validated by Pydantic.

        Returns:
            Verified counts, percentages, and source identities.
        """
        request = IncidentAnalysisRequest.model_validate(dict(arguments))
        filtered = [
            record
            for record in request.records
            if (
                request.date_from is None
                or record.incident_date >= request.date_from
            )
            and (
                request.date_to is None
                or record.incident_date <= request.date_to
            )
        ]
        grouped: dict[str, list[IncidentEvidence]] = defaultdict(list)
        for record in filtered:
            grouped[record.incident_id].append(record)

        incidents = [
            self._deduplicate_incident(records)
            for _, records in sorted(grouped.items())
        ]
        classified: dict[RootCauseCategory, list[IncidentSourceReference]] = (
            defaultdict(list)
        )
        unknown_count = 0
        unclassified_count = 0
        all_sources: list[IncidentSourceReference] = []
        for incident, category, incident_category in incidents:
            if incident_category is None:
                unclassified_count += 1
            if category is None:
                unknown_count += 1
                continue
            classified[category].extend(incident)

        for sources in classified.values():
            all_sources.extend(sources)
        if unknown_count:
            for source_list, category, _incident_category in incidents:
                if category is None:
                    all_sources.extend(source_list)

        classified_incidents = sum(
            1
            for _sources, category, _incident_category in incidents
            if category is not None
        )
        causes = [
            RootCauseFrequency(
                category=category,
                incident_count=len({source.incident_id for source in sources}),
                percentage=round(
                    len({source.incident_id for source in sources})
                    * 100
                    / classified_incidents,
                    2,
                ),
                sources=sources,
            )
            for category, sources in sorted(classified.items())
        ]
        return IncidentAnalysisResult(
            incidents_analyzed=len(incidents),
            date_from=request.date_from,
            date_to=request.date_to,
            root_causes=causes,
            unknown_root_cause_count=unknown_count,
            unclassified_incident_count=unclassified_count,
            sources=all_sources,
        )

    @staticmethod
    def _deduplicate_incident(
        records: list[IncidentEvidence],
    ) -> tuple[list[IncidentSourceReference], RootCauseCategory | None,
               IncidentCategory | None]:
        """Collapse duplicate chunks and mark conflicting labels unknown.

        Args:
            records: Chunks sharing one source incident ID.

        Returns:
            Source references, one consistent cause label if available, and
            one consistent incident category if available.
        """
        unique_records = {
            (record.source_document_id, record.source_chunk_id): record
            for record in records
        }
        causes = {
            record.root_cause_category
            for record in unique_records.values()
            if record.root_cause_category is not None
        }
        categories = {
            record.incident_category
            for record in unique_records.values()
            if record.incident_category is not None
        }
        incident_id = records[0].incident_id
        sources = [
            IncidentSourceReference(
                incident_id=incident_id,
                document_id=record.source_document_id,
                chunk_id=record.source_chunk_id,
                incident_date=record.incident_date,
            )
            for record in sorted(
                unique_records.values(),
                key=lambda item: (item.source_document_id,
                                  item.source_chunk_id),
            )
        ]
        return (
            sources,
            next(iter(causes)) if len(causes) == 1 else None,
            next(iter(categories)) if len(categories) == 1 else None,
        )
