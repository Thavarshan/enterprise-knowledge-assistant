"""Search the configured corpus with a local BM25 Okapi ranker.

This sparse adapter builds term statistics from synthetic or explicitly
configured chunks at startup. It applies trusted access and department
filters before scoring results that can enter graph state.
"""

import math
import re
from collections import Counter
from collections.abc import Sequence

from enterprise_assistant.domain.models import DocumentChunk, SearchResult

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


class BM25Retriever:
    """Rank an immutable corpus using BM25 Okapi term statistics.

    Document IDs and titles are indexed with content so exact incident IDs
    are searchable. Search results retain their validated source metadata.

    Attributes:
        document_count: Number of validated chunks in the local corpus.
    """

    def __init__(
        self,
        chunks: Sequence[DocumentChunk],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        """Build stable term-frequency and inverse-document-frequency maps.

        Args:
            chunks: Validated chunks searched by the local sparse index.
            k1: Positive term-frequency saturation constant.
            b: Length normalization between zero and one.

        Raises:
            ValueError: BM25 parameters fall outside their valid ranges.
        """
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("BM25 parameters are outside their valid range.")
        self._chunks = tuple(chunks)
        self._k1 = k1
        self._b = b
        self._term_frequencies: tuple[Counter[str], ...] = tuple(
            Counter(self._document_tokens(chunk)) for chunk in self._chunks
        )
        self._document_lengths = tuple(
            sum(frequencies.values())
            for frequencies in self._term_frequencies
        )
        self._average_length = (
            sum(self._document_lengths) / len(self._document_lengths)
            if self._document_lengths
            else 1.0
        )
        document_frequency: Counter[str] = Counter()
        for frequencies in self._term_frequencies:
            document_frequency.update(frequencies.keys())
        self._inverse_document_frequency = {
            term: math.log(
                1
                + (
                    len(self._chunks) - frequency + 0.5
                )
                / (frequency + 0.5)
            )
            for term, frequency in document_frequency.items()
        }

    @property
    def document_count(self) -> int:
        """Return the number of chunks represented in this sparse index.

        Returns:
            Count of validated source chunks.
        """
        return len(self._chunks)

    async def search_sparse(
        self,
        query: str,
        *,
        allowed_access_levels: frozenset[str],
        department: str | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Return top BM25 matches within trusted metadata filters.

        Args:
            query: User or research subtask terms.
            allowed_access_levels: Backend-derived access labels.
            department: Optional trusted department constraint.
            limit: Maximum number of chunks returned.

        Returns:
            Ranked sparse results with normalized non-negative scores.
        """
        if limit <= 0 or not allowed_access_levels:
            return []
        query_terms = Counter(_TOKEN_PATTERN.findall(query.casefold()))
        if not query_terms:
            return []
        ranked: list[tuple[float, int]] = []
        for index, chunk in enumerate(self._chunks):
            metadata = chunk.metadata
            if metadata.access_level not in allowed_access_levels:
                continue
            if department is not None and metadata.department != department:
                continue
            score = self._score(index, query_terms)
            if score > 0:
                ranked.append((score, index))
        ranked.sort(
            key=lambda item: (
                -item[0],
                self._chunks[item[1]].metadata.document_id,
                self._chunks[item[1]].metadata.chunk_id,
            )
        )
        highest = ranked[0][0] if ranked else 1.0
        return [
            SearchResult(
                chunk=self._chunks[index],
                score=score / highest,
                rank=rank,
            )
            for rank, (score, index) in enumerate(ranked[:limit], start=1)
        ]

    def _score(self, index: int, query_terms: Counter[str]) -> float:
        """Calculate the BM25 score for one pre-filtered document.

        Args:
            index: Position of a chunk in the immutable local corpus.
            query_terms: Query term frequencies from the caller.

        Returns:
            Non-negative BM25 score for the selected chunk.
        """
        frequencies = self._term_frequencies[index]
        length = self._document_lengths[index]
        normalization = self._k1 * (
            1 - self._b + self._b * length / self._average_length
        )
        score = 0.0
        for term, query_frequency in query_terms.items():
            term_frequency = frequencies.get(term, 0)
            if not term_frequency:
                continue
            inverse_frequency = self._inverse_document_frequency.get(term, 0)
            numerator = term_frequency * (self._k1 + 1)
            score += (
                inverse_frequency
                * numerator
                / (term_frequency + normalization)
                * min(query_frequency, 2)
            )
        return score

    @staticmethod
    def _document_tokens(chunk: DocumentChunk) -> list[str]:
        """Tokenize stable IDs, title, department, and chunk content.

        Args:
            chunk: Validated source chunk to add to the sparse index.

        Returns:
            Lowercase alphanumeric terms used by BM25.
        """
        metadata = chunk.metadata
        text = (
            f"{metadata.document_id} {metadata.chunk_id} {metadata.title} "
            f"{metadata.department} {chunk.content}"
        )
        return _TOKEN_PATTERN.findall(text.casefold())
