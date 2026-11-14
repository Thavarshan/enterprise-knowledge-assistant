"""Deterministic fixture-backed retrieval for local use and automated tests."""

import json
import re
from pathlib import Path
from typing import Any

from enterprise_assistant.domain.models import DocumentChunk, SearchResult

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


class InMemoryRetriever:
    def __init__(self, chunks: list[DocumentChunk]) -> None:
        self._chunks = tuple(chunks)

    @classmethod
    def from_json(cls, path: Path | None = None) -> "InMemoryRetriever":
        source = path or Path.cwd() / "data" / "samples" / "documents.json"
        raw_documents: Any = json.loads(source.read_text(encoding="utf-8"))
        return cls([DocumentChunk.model_validate(document) for document in raw_documents])

    async def search(
        self,
        query: str,
        *,
        allowed_access_levels: frozenset[str],
        department: str | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Filter access metadata before reading candidates into ranked evidence."""
        if limit <= 0:
            return []
        query_terms = set(_TOKEN_PATTERN.findall(query.casefold()))
        ranked: list[tuple[int, DocumentChunk]] = []
        for chunk in self._chunks:
            metadata = chunk.metadata
            if metadata.access_level not in allowed_access_levels:
                continue
            if department is not None and metadata.department != department:
                continue
            searchable = f"{metadata.title} {chunk.content}".casefold()
            overlap = sum(1 for token in _TOKEN_PATTERN.findall(searchable) if token in query_terms)
            if overlap:
                ranked.append((overlap, chunk))
        ranked.sort(key=lambda item: (-item[0], item[1].metadata.document_id))
        highest = ranked[0][0] if ranked else 1
        return [
            SearchResult(chunk=chunk, score=count / highest, rank=rank)
            for rank, (count, chunk) in enumerate(ranked[:limit], start=1)
        ]

    def contains_chunk(self, chunk_id: str) -> bool:
        return any(chunk.metadata.chunk_id == chunk_id for chunk in self._chunks)
