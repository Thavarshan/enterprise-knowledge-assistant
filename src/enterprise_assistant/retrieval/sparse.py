"""Contract for a future BM25 or Pinecone sparse retrieval implementation."""

from collections.abc import Sequence
from typing import Protocol

from enterprise_assistant.domain.models import SearchResult


class SparseRetriever(Protocol):
    async def search_sparse(
        self,
        query: str,
        *,
        allowed_access_levels: frozenset[str],
        limit: int,
    ) -> Sequence[SearchResult]: ...
