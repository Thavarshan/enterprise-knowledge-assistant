"""Score-safe reciprocal-rank fusion for dense and sparse results."""

from collections import defaultdict
from collections.abc import Sequence

from enterprise_assistant.domain.models import SearchResult


def reciprocal_rank_fusion(
    result_lists: Sequence[Sequence[SearchResult]], *, rank_constant: int = 60
) -> list[SearchResult]:
    """Merge ranked result lists without comparing incompatible raw scores."""
    if rank_constant <= 0:
        raise ValueError("rank_constant must be positive")
    fused_scores: dict[str, float] = defaultdict(float)
    chunks: dict[str, SearchResult] = {}
    for results in result_lists:
        for position, result in enumerate(results, start=1):
            chunk_id = result.chunk.metadata.chunk_id
            fused_scores[chunk_id] += 1 / (rank_constant + position)
            chunks.setdefault(chunk_id, result)
    ordered = sorted(
        chunks, key=lambda chunk_id: (-fused_scores[chunk_id], chunk_id))
    return [
        SearchResult(chunk=chunks[chunk_id].chunk,
                     score=fused_scores[chunk_id], rank=rank)
        for rank, chunk_id in enumerate(ordered, start=1)
    ]
