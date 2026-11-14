"""Interfaces for retrieval and the future document indexing pipeline."""

from collections.abc import Sequence
from typing import Protocol

from enterprise_assistant.domain.models import DocumentChunk, SearchResult


class RetrievalFilters(Protocol):
    allowed_access_levels: frozenset[str]
    department: str | None


class Retriever(Protocol):
    async def search(
        self,
        query: str,
        *,
        allowed_access_levels: frozenset[str],
        department: str | None = None,
        limit: int = 5,
    ) -> Sequence[SearchResult]: ...


class DocumentLoader(Protocol):
    async def load(self, source: str) -> Sequence[DocumentChunk]: ...


class Chunker(Protocol):
    def chunk(self, document: DocumentChunk) -> Sequence[DocumentChunk]: ...


class Embedder(Protocol):
    async def embed_dense(
        self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class SparseIndexer(Protocol):
    async def index_sparse(self, chunks: Sequence[DocumentChunk]) -> None: ...


class HybridRanker(Protocol):
    def fuse(
        self,
        result_lists: Sequence[Sequence[SearchResult]],
    ) -> Sequence[SearchResult]: ...
