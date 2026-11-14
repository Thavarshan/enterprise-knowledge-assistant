"""Verify Pinecone ingestion, filtering, and BM25/RRF local behavior.

The unit tests use SDK-compatible mocks and the synthetic incident corpus.
They do not contact Pinecone or disclose restricted chunk content.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from enterprise_assistant.retrieval.bm25 import BM25Retriever
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever
from enterprise_assistant.retrieval.pinecone import (
    PineconeConfig,
    PineconeRetriever,
)


def _corpus() -> InMemoryRetriever:
    """Load the synthetic incident corpus used by local tests.

    Returns:
        A validated in-memory corpus without production or customer data.
    """
    return InMemoryRetriever.from_json(
        Path("data/samples/incident_corpus.json")
    )


def _fake_pinecone_client(
    metadata: list[dict[str, object]],
) -> tuple[Mock, Mock]:
    """Create an SDK-shaped client returning fixed synthetic results.

    Args:
        metadata: Metadata values attached to fake vector matches.

    Returns:
        Fake client and index objects for adapter behavior assertions.
    """
    client = Mock()
    index = Mock()
    client.describe_index.return_value = SimpleNamespace(
        status=SimpleNamespace(ready=True),
        host="synthetic-index-host",
        schema=SimpleNamespace(
            fields={
                "chunk_text": SimpleNamespace(
                    embed=SimpleNamespace(
                        model="llama-text-embed-v2",
                        dimension=1024,
                    ),
                    full_text_search=object(),
                ),
                "title": SimpleNamespace(),
            }
        ),
    )
    client.Index.return_value = index
    index.documents.search.return_value = SimpleNamespace(
        matches=[
            SimpleNamespace(**item, score=0.9 - rank / 10)
            for rank, item in enumerate(metadata)
        ]
    )
    return client, index


@pytest.mark.asyncio
async def test_bm25_finds_exact_incident_id_and_filters_access() -> None:
    """Verify exact sparse IDs work and unauthorized chunks stay hidden.

    Metadata filters use backend-derived labels before a sparse result can
    be returned to a graph node.
    """
    corpus = _corpus()
    retriever = BM25Retriever(corpus.chunks)

    exact = await retriever.search_sparse(
        "INC-2026-057",
        allowed_access_levels=frozenset({"viewer", "analyst"}),
        limit=3,
    )
    restricted = await retriever.search_sparse(
        "INC-2025-203",
        allowed_access_levels=frozenset({"viewer"}),
        limit=3,
    )

    assert exact[0].chunk.metadata.document_id == "incident-2026-057"
    assert not any(
        item.chunk.metadata.document_id == "incident-2025-203"
        for item in restricted
    )


@pytest.mark.asyncio
async def test_pinecone_query_applies_and_rechecks_access_filter() -> None:
    """Verify provider filtering and local filtering both deny restricted data.

    The fake provider deliberately returns one restricted match to prove the
    adapter rechecks the access label before constructing graph evidence.
    """
    corpus = _corpus()
    allowed = PineconeRetriever._document(corpus.chunks[0])
    restricted = PineconeRetriever._document(corpus.chunks[2])
    client, index = _fake_pinecone_client([allowed, restricted])
    retriever = PineconeRetriever(
        PineconeConfig("synthetic-key", "synthetic-index", "assessment-demo"),
        client=client,
    )

    results = await retriever.search(
        "payment callbacks delayed",
        allowed_access_levels=frozenset({"viewer"}),
        department="payments",
        limit=5,
    )

    query_filter = index.documents.search.call_args.kwargs["filter"]
    assert query_filter == {
        "access_level": {"$in": ["viewer"]},
        "department": {"$eq": "payments"},
    }
    assert len(results) == 1
    assert results[0].chunk.metadata.access_level == "viewer"
    assert results[0].chunk.content == corpus.chunks[0].content
    score = index.documents.search.call_args.kwargs["score_by"][0]
    assert type(score).__name__ == "EmbedQuery"

    sparse_results = await retriever.search_sparse(
        "INC-2026-057",
        allowed_access_levels=frozenset({"viewer"}),
        limit=5,
    )
    sparse_score = index.documents.search.call_args.kwargs["score_by"][0]

    assert sparse_results
    assert type(sparse_score).__name__ == "TextQuery"


@pytest.mark.asyncio
async def test_pinecone_ingestion_uses_stable_ids_and_namespace() -> None:
    """Verify ingestion writes vectors using complete source identities.

    Repeated source ingestion upserts stable IDs into the configured
    assessment namespace and keeps provenance metadata with each vector.
    """
    chunk = _corpus().chunks[0]
    client, index = _fake_pinecone_client([])
    retriever = PineconeRetriever(
        PineconeConfig("synthetic-key", "synthetic-index", "assessment-demo"),
        client=client,
    )

    count = await retriever.upsert_documents([chunk])
    documents = index.documents.upsert.call_args.kwargs["documents"]

    assert count == 1
    assert documents[0]["_id"] == (
        "incident-2026-057::incident-2026-057-001"
    )
    assert documents[0]["chunk_text"] == chunk.content
    assert (
        index.documents.upsert.call_args.kwargs["namespace"]
        == "assessment-demo"
    )
