"""Define contracts for retrieval and future document indexing stages.

The protocols separate loading, chunking, dense embedding, sparse indexing,
search, and rank fusion. Only the in-memory search adapter currently
implements an end-to-end retrieval path.
"""

from collections.abc import Sequence
from typing import Protocol

from enterprise_assistant.domain.models import DocumentChunk, SearchResult


class RetrievalFilters(Protocol):
    """Describe trusted filters accepted by a retrieval adapter.

    This protocol carries allowed access labels and an optional exact
    department constraint. The current Retriever signature passes these
    values as keyword arguments rather than accepting this object.

    Attributes:
        allowed_access_levels: Backend-derived access labels.
        department: Optional exact department restriction.
    """

    allowed_access_levels: frozenset[str]
    department: str | None


class Retriever(Protocol):
    """Define the async search contract shared by graph adapters.

    Implementations must apply trusted access and department filters before
    returning content. Scores are adapter-specific and results must retain
    stable document and chunk attribution.
    """

    async def search(
        self,
        query: str,
        *,
        allowed_access_levels: frozenset[str],
        department: str | None = None,
        limit: int = 5,
    ) -> Sequence[SearchResult]:
        """Search for ranked chunks within trusted access filters.

        Args:
            query: User or planner query string.
            allowed_access_levels: Backend-derived labels the user may read.
            department: Optional exact department filter.
            limit: Maximum result count.

        Returns:
            Ranked results with source metadata.
        """
        ...


class DocumentLoader(Protocol):
    """Define the boundary for loading external or local source documents.

    No concrete loader is connected to the current API.
    """

    async def load(self, source: str) -> Sequence[DocumentChunk]:
        """Load source content into document-chunk values.

        Args:
            source: Configured path or external source identifier.

        Returns:
            Loaded chunks with metadata.
        """
        ...


class Chunker(Protocol):
    """Define the boundary for splitting documents into indexable chunks.

    A production implementation must preserve parent provenance and stable
    chunk identifiers across indexing and citation generation.
    """

    def chunk(self, document: DocumentChunk) -> Sequence[DocumentChunk]:
        """Split one document value into indexable chunks.

        Args:
            document: Source document content and metadata.

        Returns:
            Ordered chunks preserving document attribution.
        """
        ...


class Embedder(Protocol):
    """Define an asynchronous dense embedding provider contract.

    No embedding model or provider is instantiated in the current app.
    """

    async def embed_dense(
        self, texts: Sequence[str]
    ) -> Sequence[Sequence[float]]:
        """Create dense vectors for a sequence of texts.

        Args:
            texts: Text values in request order.

        Returns:
            Vectors aligned positionally with the supplied text values.
        """
        ...


class SparseIndexer(Protocol):
    """Define the contract for writing sparse retrieval records.

    The interface does not currently imply a BM25 implementation or index.
    """

    async def index_sparse(self, chunks: Sequence[DocumentChunk]) -> None:
        """Index sparse representations for supplied chunks.

        Args:
            chunks: Source chunks whose sparse terms should be indexed.
        """
        ...


class HybridRanker(Protocol):
    """Define a result-fusion interface for independent ranked lists.

    Fusion should preserve chunk identity and attribution while producing a
    single ordered result sequence.
    """

    def fuse(
        self,
        result_lists: Sequence[Sequence[SearchResult]],
    ) -> Sequence[SearchResult]:
        """Combine ranked candidate lists into one ranking.

        Args:
            result_lists: Ordered result sequences from separate retrievers.

        Returns:
            One fused sequence of ranked results.
        """
        ...
