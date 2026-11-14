"""Deterministic grounded response construction for the Response graph node."""

from enterprise_assistant.domain.models import SearchResult, SourceCitation


def grounded_response(
    results: list[SearchResult],
) -> tuple[str, list[SourceCitation]]:
    """Build response text and citations only from retrieved chunk objects."""
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
