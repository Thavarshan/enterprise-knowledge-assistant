"""Validated document and citation contracts shared across modules."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AccessLevel = Literal["viewer", "analyst", "administrator"]


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    department: str = Field(min_length=1)
    document_type: str = Field(min_length=1)
    access_level: AccessLevel
    created_date: date
    source: str = Field(min_length=1)


class DocumentChunk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str = Field(min_length=1)
    metadata: DocumentMetadata


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk: DocumentChunk
    score: float = Field(ge=0)
    rank: int = Field(ge=1)


class SourceCitation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    chunk_id: str
    title: str
    source: str

    @classmethod
    def from_chunk(cls, chunk: DocumentChunk) -> "SourceCitation":
        metadata = chunk.metadata
        return cls(
            document_id=metadata.document_id,
            chunk_id=metadata.chunk_id,
            title=metadata.title,
            source=metadata.source,
        )
