"""Verify labeled retrieval metrics and source/access accounting.

The evaluator uses small synthetic result lists so ranking definitions stay
deterministic without contacting Pinecone.
"""

from scripts.evaluate_retrieval import (
    EvaluationCase,
    EvaluationDataset,
    score_rankings,
)

from enterprise_assistant.domain.models import (
    DocumentChunk,
    DocumentMetadata,
    SearchResult,
)


def _result(document_id: str, access_level: str) -> SearchResult:
    """Build one synthetic ranked source with complete metadata.

    Args:
        document_id: Stable test document identity.
        access_level: Source label checked against the query role.

    Returns:
        One result that can be scored by the retrieval evaluator.
    """
    chunk = DocumentChunk(
        content="Synthetic test evidence.",
        metadata=DocumentMetadata(
            document_id=document_id,
            chunk_id=f"{document_id}-001",
            title=f"Synthetic {document_id}",
            department="payments",
            document_type="incident_report",
            access_level=access_level,
            created_date="2026-01-01",
            source=f"sample://{document_id}",
        ),
    )
    return SearchResult(chunk=chunk, score=1.0, rank=1)


def test_retrieval_metrics_track_recall_attribution_and_access_leaks() -> None:
    """Score relevant retrieval and detect a forbidden result explicitly.

    The result list deliberately contains one unauthorized identity to
    prove the metric can detect adapter leaks.
    """
    dataset = EvaluationDataset(
        version=1,
        cases=[
            EvaluationCase(
                case_id="relevant",
                query="INC-1",
                role="analyst",
                expected_document_ids=["doc-1"],
                expected_empty=False,
            ),
            EvaluationCase(
                case_id="restricted-empty",
                query="INC-2",
                role="viewer",
                forbidden_document_ids=["doc-2"],
            ),
            EvaluationCase(
                case_id="empty",
                query="no results",
                role="viewer",
                expected_empty=True,
            ),
        ],
    )
    relevant = _result("doc-1", "viewer")
    forbidden = _result("doc-2", "analyst")

    report = score_rankings(
        "test",
        dataset,
        [[relevant], [forbidden], []],
        known_identities=frozenset({("doc-1", "doc-1-001")}),
        limit=5,
    )

    assert report.recall_at_k == 1.0
    assert report.mrr == 1.0
    assert report.source_attribution_accuracy == 0.5
    assert report.access_control_leakage_rate == 0.5
    assert report.empty_result_accuracy == 1.0
    assert report.cases[1].unauthorized_document_ids == ["doc-2"]
