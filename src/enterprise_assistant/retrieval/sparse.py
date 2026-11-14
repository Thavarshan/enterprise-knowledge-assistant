"""Define the future sparse-search contract.

The protocol describes an asynchronous query with trusted access filters
and a result limit. No BM25 index or sparse provider is connected in the
current application.
"""

from collections.abc import Sequence
from typing import Protocol

from enterprise_assistant.domain.models import SearchResult


class SparseRetriever(Protocol):
    """Define the async sparse-search contract for future adapters.

    A concrete implementation should apply access restrictions before
    exposing chunk content and retain provenance in returned results. No
    sparse index is connected in the current graph.
    """

    async def search_sparse(
        self,
        query: str,
        *,
        allowed_access_levels: frozenset[str],
        limit: int,
    ) -> Sequence[SearchResult]:
        """Search an indexed sparse representation of the query.

        Args:
            query: Query text for lexical or sparse-vector matching.
            allowed_access_levels: Trusted access labels allowed for results.
            limit: Maximum number of chunks to return.

        Returns:
            Ranked sparse-search results with original chunk metadata.
        """
        ...
