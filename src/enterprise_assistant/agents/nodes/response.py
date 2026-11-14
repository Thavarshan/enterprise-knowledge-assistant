"""Create a deterministic answer from retrieved evidence.

The response node selects at most two ranked chunks and derives each
citation from that chunk's metadata. It returns a fixed no-result message
when retrieval produces no accessible evidence; no LLM is involved.
"""

from enterprise_assistant.domain.models import SearchResult, SourceCitation


def grounded_response(
    results: list[SearchResult],
) -> tuple[str, list[SourceCitation]]:
    """Construct answer text and citations from retrieved evidence.

    At most the first two ranked results are included. Each marker is
    built from the chunk used to construct its SourceCitation.

    Args:
        results: Ranked results returned by authorized retrieval.

    Returns:
        Response text paired with the citations used in that text.

    Notes:
        This deterministic function does not call a language model.
    """
    selected = results[:2]
    citations = [SourceCitation.from_chunk(result.chunk) for result in selected]
    if not selected:
        return (
            "I could not find an accessible document "
            "that answers this question.",
            [],
        )
    answer = "\n\n".join(
        f"{result.chunk.content} [{citation.document_id}#{citation.chunk_id}]"
        for result, citation in zip(selected, citations, strict=True)
    )
    return answer, citations
