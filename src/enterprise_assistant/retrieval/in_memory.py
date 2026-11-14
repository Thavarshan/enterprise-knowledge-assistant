"""Search validated fixture chunks deterministically for local use and tests.

The adapter applies access-level and optional department filters before
lexical scoring, then returns ranked chunks with stable metadata. Its token
overlap score is a mock relevance signal, not a production BM25 or embedding
score.
"""

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from enterprise_assistant.domain.models import DocumentChunk, SearchResult

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


class InMemoryRetriever:
    """Search fixture chunks with deterministic lexical overlap.

    The adapter stores an immutable tuple of chunks and applies access
    and department filters before scoring. It is intended for local
    demos and tests, not production relevance evaluation.

    Attributes:
        _chunks: Tuple of chunks searched by this adapter.

    Concurrency:
        The async method performs a small synchronous scan; it does not
        offload work to a thread.
    """

    def __init__(self, chunks: list[DocumentChunk]) -> None:
        """Store the supplied chunks as an immutable tuple.

        The caller can validate schemas before construction or use
        from_json.

        Args:
            chunks: Validated document chunks to search.
        """
        self._chunks = tuple(chunks)

    @property
    def chunks(self) -> tuple[DocumentChunk, ...]:
        """Expose the validated immutable corpus for alternate rankers.

        Returns:
            Source chunks in their configured document order.
        """
        return self._chunks

    @classmethod
    def from_json(cls, path: Path | None = None) -> "InMemoryRetriever":
        """Load fixture chunks from a supplied or repository-default JSON file.

        Each record is validated as a DocumentChunk. File, decoding, and
        schema errors propagate rather than causing a silent provider
        fallback.

        Args:
            path: Optional fixture path; defaults to
            data/samples/documents.json.

        Returns:
            A retriever containing the validated fixture chunks.

        Raises:
            OSError: The selected fixture file cannot be read.
            ValidationError: A record violates the chunk schema.
        """
        source = path or Path.cwd() / "data" / "samples" / "documents.json"
        raw_documents: Any = json.loads(source.read_text(encoding="utf-8"))
        chunks = [
            DocumentChunk.model_validate(document)
            for document in raw_documents
        ]
        return cls(chunks)

    async def search(
        self,
        query: str,
        *,
        allowed_access_levels: frozenset[str],
        department: str | None = None,
        document_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Filter authorized chunks and score token overlap for top results.

        Access and department checks happen before content is scored. Query
        tokens are deduplicated; matching token occurrences in title or
        content contribute to the count. Scores are scaled by the best
        candidate.

        Args:
            query: Text tokenized for the lexical demo score.
            allowed_access_levels: Trusted access labels from backend role.
            department: Optional exact department restriction.
            document_type: Optional exact document type restriction.
            date_from: Inclusive lower source-date boundary.
            date_to: Inclusive upper source-date boundary.
            limit: Maximum number of ranked results.

        Returns:
            Accessible chunks ordered by overlap with score and rank fields.

        Notes:
            Non-positive limits return no results. Equal scores use document
            ID ordering; this heuristic is not BM25.
        """
        if limit <= 0:
            return []
        query_terms = set(_TOKEN_PATTERN.findall(query.casefold()))
        ranked: list[tuple[int, DocumentChunk]] = []
        for chunk in self._chunks:
            metadata = chunk.metadata
            # Apply trusted scope before examining content or computing rank.
            if metadata.access_level not in allowed_access_levels:
                continue
            if department is not None and metadata.department != department:
                continue
            if (
                document_type is not None
                and metadata.document_type != document_type
            ):
                continue
            if date_from is not None and metadata.created_date < date_from:
                continue
            if date_to is not None and metadata.created_date > date_to:
                continue
            searchable = f"{metadata.title} {chunk.content}".casefold()
            overlap = sum(1 for token in _TOKEN_PATTERN.findall(
                searchable) if token in query_terms)
            if overlap:
                ranked.append((overlap, chunk))
        ranked.sort(key=lambda item: (-item[0], item[1].metadata.document_id))
        highest = ranked[0][0] if ranked else 1
        return [
            SearchResult(chunk=chunk, score=count / highest, rank=rank)
            for rank, (count, chunk) in enumerate(ranked[:limit], start=1)
        ]

    def contains_chunk(self, chunk_id: str) -> bool:
        """Check whether a chunk identifier exists in the stored fixtures.

        The lookup supports lineage checks without copying chunk content.

        Args:
            chunk_id: Identifier to locate.

        Returns:
            True when a stored chunk has that identifier.
        """
        return any(
            chunk.metadata.chunk_id == chunk_id for chunk in self._chunks
        )
