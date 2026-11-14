"""Combine dense and BM25 results with reciprocal rank fusion.

The Pinecone index is dense cosine, so this layer fuses its ranked results
with local BM25 rankings. Stable document/chunk pairs deduplicate candidates
without comparing unrelated raw score scales.
"""

import asyncio
from collections import defaultdict
from collections.abc import Sequence
from datetime import date

from enterprise_assistant.domain.models import SearchResult
from enterprise_assistant.retrieval.interfaces import Retriever
from enterprise_assistant.retrieval.sparse import SparseRetriever


class HybridRetriever:
    """Fuse one dense adapter and one BM25 adapter into a ranked list.

    The dense provider applies Pinecone metadata filters, while BM25 applies
    the same trusted filters locally before ranking. Both are required for
    this adapter to return a hybrid result.

    Attributes:
        dense: Adapter returning semantically ranked evidence.
        sparse: Local BM25 adapter returning lexical rankings.
        rank_constant: Positive RRF stabilizer shared by both rankings.
    """

    def __init__(
        self,
        dense: Retriever,
        sparse: SparseRetriever,
        *,
        rank_constant: int = 60,
    ) -> None:
        """Store dense and sparse adapters for concurrent retrieval.

        Args:
            dense: Pinecone-backed dense retriever.
            sparse: Local BM25 retriever over the same corpus.
            rank_constant: Positive position stabilizer for RRF.

        Raises:
            ValueError: The RRF rank constant is zero or negative.
        """
        if rank_constant <= 0:
            raise ValueError("rank_constant must be positive")
        self.dense = dense
        self.sparse = sparse
        self.rank_constant = rank_constant

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
        """Retrieve and fuse authorized dense and sparse candidate lists.

        Args:
            query: User or research search text.
            allowed_access_levels: Server-derived labels allowed for the user.
            department: Optional trusted department restriction.
            document_type: Optional trusted document-type restriction.
            date_from: Inclusive lower source-date boundary.
            date_to: Inclusive upper source-date boundary.
            limit: Maximum number of fused results returned.

        Returns:
            RRF-ranked results with stable source metadata.
        """
        if limit <= 0 or not allowed_access_levels:
            return []
        candidate_limit = min(max(limit * 3, limit), 20)
        dense_results, sparse_results = await asyncio.gather(
            self.dense.search(
                query,
                allowed_access_levels=allowed_access_levels,
                department=department,
                document_type=document_type,
                date_from=date_from,
                date_to=date_to,
                limit=candidate_limit,
            ),
            self.sparse.search_sparse(
                query,
                allowed_access_levels=allowed_access_levels,
                department=department,
                document_type=document_type,
                date_from=date_from,
                date_to=date_to,
                limit=candidate_limit,
            ),
        )
        fused = reciprocal_rank_fusion(
            [dense_results, sparse_results],
            rank_constant=self.rank_constant,
        )
        return fused[:limit]


def reciprocal_rank_fusion(
    result_lists: Sequence[Sequence[SearchResult]], *, rank_constant: int = 60
) -> list[SearchResult]:
    """Fuse ranked lists using position contributions instead of raw scores.

    For each occurrence, add 1 / (rank_constant + position). Duplicate
    chunks accumulate evidence; ties use chunk ID, and the first result
    object supplies the chunk payload.

    Args:
        result_lists: Ordered candidate lists from independent
        retrievers.
        rank_constant: Positive stabilizer applied to each position.

    Returns:
        Fused results with new scores and one-based ranks.

    Raises:
        ValueError: The rank constant is zero or negative.

    Design Rationale:
        Dense similarity and sparse term scores use different scales;
        RRF compares positions rather than treating those values as
        equal.
    """
    if rank_constant <= 0:
        raise ValueError("rank_constant must be positive")
    fused_scores: dict[tuple[str, str], float] = defaultdict(float)
    chunks: dict[tuple[str, str], SearchResult] = {}
    # Ranks are comparable across providers even when raw score scales are
    # not; repeated appearance is evidence that independent searches agree.
    for results in result_lists:
        for position, result in enumerate(results, start=1):
            metadata = result.chunk.metadata
            identity = (metadata.document_id, metadata.chunk_id)
            fused_scores[identity] += 1 / (rank_constant + position)
            chunks.setdefault(identity, result)
    ordered = sorted(
        chunks,
        key=lambda identity: (
            -fused_scores[identity],
            identity[0],
            identity[1],
        ),
    )
    return [
        SearchResult(
            chunk=chunks[identity].chunk,
            score=fused_scores[identity],
            rank=rank,
        )
        for rank, identity in enumerate(ordered, start=1)
    ]
