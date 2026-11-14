"""Combine ranked result lists with reciprocal rank fusion.

RRF sums position-based contributions so dense and sparse scores do not
need to share a numeric scale. This implementation is an available ranking
utility; the current graph uses only the fixture retriever.
"""

from collections import defaultdict
from collections.abc import Sequence

from enterprise_assistant.domain.models import SearchResult


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
    fused_scores: dict[str, float] = defaultdict(float)
    chunks: dict[str, SearchResult] = {}
    # Ranks are comparable across providers even when raw score scales are
    # not; repeated appearance is evidence that independent searches agree.
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
