"""Define the sparse-search contract implemented by the BM25 adapter.

The protocol accepts only trusted access filters and a result limit.
`BM25Retriever` implements it over a configured local document corpus.
"""

from collections.abc import Sequence
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
        limit: int = 5,
    ) -> Sequence[SearchResult]:
        """Search an indexed sparse representation of the query.

        Args:
            query: Query text for lexical or sparse-vector matching.
            allowed_access_levels: Trusted access labels allowed for results.
            department: Optional trusted department constraint.
            limit: Maximum number of chunks to return.

        Returns:
            Ranked sparse-search results with original chunk metadata.
        """
        ...
