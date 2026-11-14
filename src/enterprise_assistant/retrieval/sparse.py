"""Define the sparse-search contract implemented by the BM25 adapter.

The protocol accepts only trusted access filters and a result limit.
`BM25Retriever` implements it over a configured local document corpus.
"""

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from enterprise_assistant.domain.models import SearchResult


class SparseRetriever(Protocol):
    """Define the async sparse-search contract used by hybrid retrieval.

    Implementations apply access restrictions before exposing chunk content
    and retain provenance in returned results.
    """

    async def search_sparse(
        self,
        query: str,
        *,
        allowed_access_levels: frozenset[str],
        department: str | None = None,
        document_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 5,
    ) -> Sequence[SearchResult]:
        """Search an indexed sparse representation of the query.

        Args:
            query: Query text for lexical or sparse-vector matching.
            allowed_access_levels: Trusted access labels allowed for results.
            department: Optional trusted department constraint.
            document_type: Optional exact document type constraint.
            date_from: Inclusive lower source-date boundary.
            date_to: Inclusive upper source-date boundary.
            limit: Maximum number of chunks to return.

        Returns:
            Ranked sparse-search results with original chunk metadata.
        """
        ...
