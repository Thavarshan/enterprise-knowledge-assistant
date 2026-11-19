"""Evaluate Pinecone rankings on the checked-in synthetic query set.

The opt-in report compares provider dense, BM25, and RRF results using
recall@k, MRR, source attribution, authorization leakage, and empty-result
accuracy. It reports IDs and metrics only, not retrieved source content.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable, Sequence
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from enterprise_assistant.config.settings import get_settings
from enterprise_assistant.domain.models import SearchResult
from enterprise_assistant.retrieval.hybrid import HybridRetriever
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever
from enterprise_assistant.retrieval.pinecone import (
    PineconeConfig,
    PineconeRetriever,
)
from enterprise_assistant.security.authorization import Role
from enterprise_assistant.tools.knowledge import allowed_access_levels


class EvaluationCase(BaseModel):
    """Describe one labeled, synthetic retrieval query and access boundary.

    Attributes:
        case_id: Stable human-readable evaluation case identifier.
        query: Query string sent to each ranking mode.
        role: Test role mapped to access levels by backend policy.
        document_type: Optional exact metadata filter.
        department: Optional exact metadata filter.
        date_from: Inclusive lower source date, when specified.
        date_to: Inclusive upper source date, when specified.
        expected_document_ids: Relevant source document IDs for recall.
        forbidden_document_ids: Documents that this role must not see.
        expected_empty: Optional expected empty or non-empty outcome. None
            excludes cases that measure only an authorization boundary.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=1, max_length=500)
    role: Role
    document_type: str | None = None
    department: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    expected_document_ids: list[str] = Field(default_factory=list)
    forbidden_document_ids: list[str] = Field(default_factory=list)
    expected_empty: bool | None = None


class EvaluationDataset(BaseModel):
    """Validate the versioned labeled retrieval cases.

    Attributes:
        version: Dataset format version.
        cases: Synthetic queries with expected evidence and constraints.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    cases: list[EvaluationCase] = Field(min_length=1)


class CaseResult(BaseModel):
    """Report one ranking result without including document content.

    Attributes:
        case_id: Evaluation query identifier.
        ranked_document_ids: Source IDs in returned rank order.
        reciprocal_rank: Reciprocal rank of the first relevant source.
        recall_at_k: Fraction of labeled sources found in top-k.
        empty_result_correct: Whether empty/non-empty behavior matched, when
            the dataset labels that outcome.
        source_attribution_correct: Whether returned source identities exist.
        unauthorized_document_ids: Any result that violates its case scope.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    ranked_document_ids: list[str]
    reciprocal_rank: float
    recall_at_k: float
    empty_result_correct: bool | None
    source_attribution_correct: bool
    unauthorized_document_ids: list[str]


class ModeResult(BaseModel):
    """Summarize one retrieval mode across the evaluation dataset.

    Attributes:
        mode: Dense, BM25, or hybrid ranking name.
        recall_at_k: Mean recall for cases with labeled relevant sources.
        mrr: Mean reciprocal rank for those same relevant cases.
        source_attribution_accuracy: Known document/chunk pair fraction.
        access_control_leakage_rate: Unauthorized or forbidden result fraction.
        empty_result_accuracy: Correct labeled empty/non-empty case fraction.
        cases: Per-query rank and access outcome summaries.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: str
    recall_at_k: float
    mrr: float
    source_attribution_accuracy: float
    access_control_leakage_rate: float
    empty_result_accuracy: float | None
    cases: list[CaseResult]


SearchOperation = Callable[
    [EvaluationCase, frozenset[str], int], Awaitable[list[SearchResult]]
]


def score_rankings(
    mode: str,
    dataset: EvaluationDataset,
    rankings: Sequence[Sequence[SearchResult]],
    *,
    known_identities: frozenset[tuple[str, str]],
    limit: int,
) -> ModeResult:
    """Calculate transparent ranking and safety metrics for one mode.

    Args:
        mode: Ranking label displayed in the JSON report.
        dataset: Versioned query labels and role constraints.
        rankings: One result list for each dataset case, in case order.
        known_identities: Source document/chunk pairs from the corpus file.
        limit: Ranking cutoff used for recall.

    Returns:
        Per-case results and unweighted means across the query set.
    """
    if len(rankings) != len(dataset.cases):
        raise ValueError("One ranking list is required per case.")
    case_results: list[CaseResult] = []
    relevant_reciprocal_ranks: list[float] = []
    relevant_recalls: list[float] = []
    attribution_total = 0
    attribution_correct = 0
    result_total = 0
    unauthorized_total = 0
    empty_correct = 0
    empty_total = 0

    for case, raw_results in zip(dataset.cases, rankings, strict=True):
        results = list(raw_results[:limit])
        ranked_ids = [result.chunk.metadata.document_id for result in results]
        expected = set(case.expected_document_ids)
        ranks = [
            index
            for index, document_id in enumerate(ranked_ids, start=1)
            if document_id in expected
        ]
        reciprocal_rank = 1 / min(ranks) if ranks else 0.0
        recall = (
            len(expected.intersection(ranked_ids)) / len(expected)
            if (expected)
            else 0.0
        )
        if expected:
            relevant_reciprocal_ranks.append(reciprocal_rank)
            relevant_recalls.append(recall)
        empty_result_correct = None
        if case.expected_empty is not None:
            empty_result_correct = bool(results) == (not case.expected_empty)
            empty_correct += int(empty_result_correct)
            empty_total += 1
        forbidden = set(case.forbidden_document_ids)
        allowed = allowed_access_levels(case.role)
        unauthorized_ids = [
            result.chunk.metadata.document_id
            for result in results
            if (
                result.chunk.metadata.access_level not in allowed
                or result.chunk.metadata.document_id in forbidden
            )
        ]
        identity_matches = [
            (
                result.chunk.metadata.document_id,
                result.chunk.metadata.chunk_id,
            )
            in known_identities
            for result in results
        ]
        result_total += len(results)
        attribution_total += len(results)
        attribution_correct += sum(identity_matches)
        unauthorized_total += len(unauthorized_ids)
        case_results.append(
            CaseResult(
                case_id=case.case_id,
                ranked_document_ids=ranked_ids,
                reciprocal_rank=reciprocal_rank,
                recall_at_k=recall,
                empty_result_correct=empty_result_correct,
                source_attribution_correct=all(identity_matches),
                unauthorized_document_ids=unauthorized_ids,
            )
        )

    relevant_count = max(len(relevant_recalls), 1)
    return ModeResult(
        mode=mode,
        recall_at_k=sum(relevant_recalls) / relevant_count,
        mrr=sum(relevant_reciprocal_ranks) / relevant_count,
        source_attribution_accuracy=(
            attribution_correct / attribution_total
            if attribution_total
            else 1.0
        ),
        access_control_leakage_rate=(
            unauthorized_total / result_total if result_total else 0.0
        ),
        empty_result_accuracy=(
            empty_correct / empty_total if empty_total else None
        ),
        cases=case_results,
    )


async def _run_mode(
    cases: Sequence[EvaluationCase],
    search: SearchOperation,
    *,
    limit: int,
) -> list[list[SearchResult]]:
    """Run one provider ranking mode for each labeled query.

    Args:
        cases: Evaluation cases in stable dataset order.
        search: Dense, sparse, or fused adapter operation.
        limit: Maximum results requested per case.

    Returns:
        Ranked result lists aligned with the supplied cases.
    """
    results: list[list[SearchResult]] = []
    for case in cases:
        results.append(
            await search(case, allowed_access_levels(case.role), limit)
        )
    return results


def _load_dataset(path: Path) -> EvaluationDataset:
    """Read and validate the checked-in JSON evaluation labels.

    Args:
        path: JSON file containing the versioned synthetic dataset.

    Returns:
        Validated query cases.
    """
    return EvaluationDataset.model_validate_json(path.read_text())


async def _evaluate(live_ingest: bool, limit: int) -> int:
    """Compare Pinecone dense, full-text BM25, and fused search rankings.

    Args:
        live_ingest: Whether to upsert the checked-in synthetic corpus first.
        limit: Result cutoff used for all ranking metrics.

    Returns:
        Process status: zero on a completed evaluation, two when blocked.
    """
    settings = get_settings()
    missing = [
        name
        for name, value in (
            ("PINECONE_API_KEY", settings.pinecone_api_key),
            ("PINECONE_INDEX_NAME", settings.pinecone_index_name),
            ("PINECONE_NAMESPACE", settings.pinecone_namespace),
        )
        if not value.strip()
    ]
    if missing:
        print(f"BLOCKED: missing configuration: {', '.join(missing)}")
        return 2

    corpus = InMemoryRetriever.from_json(Path(settings.pinecone_documents_path))
    dense = PineconeRetriever(
        PineconeConfig(
            api_key=settings.pinecone_api_key,
            index_name=settings.pinecone_index_name,
            namespace=settings.pinecone_namespace,
            embedding_model=settings.pinecone_embedding_model,
            embedding_dimension=settings.pinecone_embedding_dimension,
            timeout_seconds=settings.pinecone_timeout_seconds,
        )
    )
    if live_ingest:
        await dense.upsert_documents(corpus.chunks)
    hybrid = HybridRetriever(dense, dense)
    dataset = _load_dataset(Path("data/evaluation/retrieval_cases.json"))

    async def dense_search(
        case: EvaluationCase,
        allowed: frozenset[str],
        result_limit: int,
    ) -> list[SearchResult]:
        """Run dense retrieval with the case's validated source filters.

        The caller supplies backend-derived allowed access labels.
        """
        return await dense.search(
            case.query,
            allowed_access_levels=allowed,
            department=case.department,
            document_type=case.document_type,
            date_from=case.date_from,
            date_to=case.date_to,
            limit=result_limit,
        )

    async def bm25_search(
        case: EvaluationCase,
        allowed: frozenset[str],
        result_limit: int,
    ) -> list[SearchResult]:
        """Run full-text BM25 with the same access and source filters.

        The provider returns only metadata-validated chunks.
        """
        return await dense.search_sparse(
            case.query,
            allowed_access_levels=allowed,
            department=case.department,
            document_type=case.document_type,
            date_from=case.date_from,
            date_to=case.date_to,
            limit=result_limit,
        )

    async def hybrid_search(
        case: EvaluationCase,
        allowed: frozenset[str],
        result_limit: int,
    ) -> list[SearchResult]:
        """Run dense and BM25 queries, then combine their ranks with RRF.

        Both component searches use the same server-derived access labels.
        """
        return await hybrid.search(
            case.query,
            allowed_access_levels=allowed,
            department=case.department,
            document_type=case.document_type,
            date_from=case.date_from,
            date_to=case.date_to,
            limit=result_limit,
        )

    modes: list[tuple[str, SearchOperation]] = [
        ("dense", dense_search),
        ("bm25", bm25_search),
        ("hybrid_rrf", hybrid_search),
    ]
    known_identities = frozenset(
        (chunk.metadata.document_id, chunk.metadata.chunk_id)
        for chunk in corpus.chunks
    )
    reports: list[ModeResult] = []
    for name, operation in modes:
        rankings = await _run_mode(dataset.cases, operation, limit=limit)
        reports.append(
            score_rankings(
                name,
                dataset,
                rankings,
                known_identities=known_identities,
                limit=limit,
            )
        )
    print(
        json.dumps(
            {
                "namespace": settings.pinecone_namespace,
                "corpus_records": len(corpus.chunks),
                "k": limit,
                "metrics": [
                    report.model_dump(mode="json") for report in reports
                ],
                "limitations": [
                    "The labels cover only synthetic assessment examples.",
                    "Four queries do not predict production relevance.",
                    "Pinecone filtering and scores may change over time.",
                ],
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    """Parse the explicit live-evaluation command-line options.

    Returns:
        Process status suitable for CI or a local assessment run.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Query the configured existing Pinecone index.",
    )
    parser.add_argument(
        "--ingest-synthetic",
        action="store_true",
        help="Upsert only the checked-in synthetic corpus before evaluation.",
    )
    parser.add_argument("--limit", type=int, default=5)
    arguments = parser.parse_args()
    if not arguments.live:
        print("BLOCKED: pass --live to run against Pinecone.")
        return 2
    if not 1 <= arguments.limit <= 20:
        print("BLOCKED: --limit must be between 1 and 20.")
        return 2
    try:
        return asyncio.run(
            _evaluate(arguments.ingest_synthetic, arguments.limit)
        )
    except Exception as exc:
        print(f"FAILED: Pinecone evaluation raised {type(exc).__name__}.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
