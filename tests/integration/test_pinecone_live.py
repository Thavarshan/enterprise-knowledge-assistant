"""Verify dense and hybrid retrieval against the configured Pinecone index.

The live check is explicitly opt-in through PINECONE_RUN_LIVE_TESTS=true. It
ingests only the synthetic incident corpus into the configured namespace.
"""

import asyncio
import os
from pathlib import Path

import pytest

from enterprise_assistant.config.settings import get_settings
from enterprise_assistant.retrieval.hybrid import HybridRetriever
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever
from enterprise_assistant.retrieval.pinecone import (
    PineconeConfig,
    PineconeRetriever,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_pinecone_ingestion_and_hybrid_quality() -> None:
    """Verify synthetic ingestion, semantic search, exact ID, and RBAC.

    The synthetic corpus and isolated namespace avoid customer content. The
    test does not create indexes or change index configuration.
    """
    if os.environ.get("PINECONE_RUN_LIVE_TESTS") != "true":
        pytest.skip("Set PINECONE_RUN_LIVE_TESTS=true to opt in.")
    settings = get_settings()
    if not (
        settings.pinecone_api_key
        and settings.pinecone_index_name
        and settings.pinecone_namespace
    ):
        pytest.skip("Pinecone credentials, index, or namespace are missing.")

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
    hybrid = HybridRetriever(dense, dense)
    await dense.upsert_documents(corpus.chunks)

    semantic_results = []
    for _attempt in range(8):
        semantic_results = await hybrid.search(
            "webhook queue saturated when processor returned "
            "503s without jitter",
            allowed_access_levels=frozenset({"viewer", "analyst"}),
            limit=5,
        )
        if semantic_results:
            break
        await asyncio.sleep(1)

    exact_results = await hybrid.search(
        "INC-2026-099",
        allowed_access_levels=frozenset({"viewer", "analyst"}),
        limit=5,
    )
    viewer_results = await hybrid.search(
        "INC-2025-203",
        allowed_access_levels=frozenset({"viewer"}),
        limit=5,
    )

    assert semantic_results
    assert semantic_results[0].chunk.metadata.document_id == "incident-2026-057"
    assert exact_results
    assert exact_results[0].chunk.metadata.document_id == "incident-2026-099"
    assert all(
        item.chunk.metadata.access_level == "viewer" for item in viewer_results
    )
