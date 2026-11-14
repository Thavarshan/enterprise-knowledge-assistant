"""Validate document metadata, chunks, ranked results, and citations.

Frozen Pydantic models reject unknown fields and invalid required values so
retrieval and graph boundaries exchange predictable structures. Access
labels are constrained to the three application roles; the models validate
data shape but do not authorize a request.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AccessLevel = Literal["viewer", "analyst", "administrator"]
IncidentCategory = Literal[
    "duplicate_authorization",
    "service_outage",
    "service_degradation",
    "settlement_delay",
    "webhook_delay",
]
RootCauseCategory = Literal[
    "connection_pool_reconnect_storm",
    "dependency_not_ready",
    "ledger_lock_contention",
    "missing_idempotency_key",
    "queue_consumer_saturation",
    "rate_limit_misconfiguration",
    "retry_without_jitter",
]
IncidentSeverity = Literal["SEV-1", "SEV-2", "SEV-3", "SEV-4"]


class DocumentMetadata(BaseModel):
    """Represent required provenance and access fields for one chunk.

    The frozen model rejects extra properties and constrains
    access_level to the three application labels. It validates shape,
    not whether a user may read a document.

    Attributes:
        document_id: Stable parent document identifier.
        chunk_id: Stable identifier used in evidence markers.
        title: Human-readable document title.
        department: Owning department for optional filtering.
        document_type: Source classification label.
        access_level: Viewer, analyst, or administrator.
        created_date: Validated source date.
        source: Attribution URI or source reference.
        incident_id: Optional incident identifier from the source record.
        incident_category: Optional source-classified incident category.
        root_cause_category: Optional explicitly classified root cause.
        severity: Optional source severity label.
        impact_summary: Optional factual impact from the source record.

    Security:
        Retrieval filters enforce authorization; this model does not.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    department: str = Field(min_length=1)
    document_type: str = Field(min_length=1)
    access_level: AccessLevel
    created_date: date
    source: str = Field(min_length=1)
    incident_id: str | None = Field(default=None, min_length=1, max_length=80)
    incident_category: IncidentCategory | None = None
    root_cause_category: RootCauseCategory | None = None
    severity: IncidentSeverity | None = None
    impact_summary: str | None = Field(
        default=None, min_length=1, max_length=500)


class DocumentChunk(BaseModel):
    """Pair non-empty chunk content with validated metadata.

    The frozen value object is the unit returned by retrieval and
    consumed by deterministic response construction.

    Attributes:
        content: Non-empty evidence text.
        metadata: Validated source and access metadata.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str = Field(min_length=1)
    metadata: DocumentMetadata


class SearchResult(BaseModel):
    """Represent a ranked chunk and its retrieval score.

    The frozen model requires a non-negative score and one-based rank.
    Score meaning depends on the adapter; consumers must not compare
    unrelated provider scales directly.

    Attributes:
        chunk: Retrieved document evidence.
        score: Non-negative adapter or fusion score.
        rank: One-based position in the result sequence.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk: DocumentChunk
    score: float = Field(ge=0)
    rank: int = Field(ge=1)


class SourceCitation(BaseModel):
    """Carry citation metadata copied from one source chunk.

    The compact value keeps stable source identifiers and display data
    without duplicating full chunk text.

    Attributes:
        document_id: Parent document identifier.
        chunk_id: Evidence chunk identifier.
        title: Display title for the citation.
        source: Source reference copied from metadata.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    chunk_id: str
    title: str
    source: str

    @classmethod
    def from_chunk(cls, chunk: DocumentChunk) -> "SourceCitation":
        """Copy attribution fields from a retrieved chunk.

        Centralizing this conversion keeps the citation aligned with the
        metadata associated with its evidence object.

        Args:
            chunk: Retrieved chunk whose source should be cited.

        Returns:
            Citation with document, chunk, title, and source fields.
        """
        metadata = chunk.metadata
        return cls(
            document_id=metadata.document_id,
            chunk_id=metadata.chunk_id,
            title=metadata.title,
            source=metadata.source,
        )
