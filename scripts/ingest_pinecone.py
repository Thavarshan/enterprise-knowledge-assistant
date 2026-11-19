"""Index synthetic assessment records in an existing Pinecone namespace.

The command upserts stable IDs through Pinecone's schema-aware Documents API.
An optional prior corpus removes only its exact obsolete IDs after the new
records are accepted. The index schema performs embedding; the command never
creates an index or logs credentials or content.
"""

import argparse
import asyncio
from pathlib import Path

from enterprise_assistant.config.settings import get_settings
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever
from enterprise_assistant.retrieval.pinecone import (
    PineconeConfig,
    PineconeRetriever,
)


def parse_args() -> argparse.Namespace:
    """Parse optional source-corpus and exact legacy-removal paths.

    Returns:
        Paths selecting the corpus to upsert and, optionally, the corpus
        whose exact record IDs should be removed after the upsert succeeds.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        help="JSON corpus to upsert; defaults to PINECONE_DOCUMENTS_PATH.",
    )
    parser.add_argument(
        "--delete-source",
        type=Path,
        help=(
            "Optional prior JSON corpus whose exact IDs should be deleted "
            "after the new corpus is upserted."
        ),
    )
    return parser.parse_args()


async def main(args: argparse.Namespace) -> None:
    """Ingest a validated source corpus into the configured namespace.

    Raises:
        PineconeNotConfigured: Required Pinecone settings are absent.
        PineconeRequestError: Indexing or embedding fails.
    """
    settings = get_settings()
    source_path = args.source or Path(settings.pinecone_documents_path)
    corpus = InMemoryRetriever.from_json(source_path)
    previous_corpus = (
        InMemoryRetriever.from_json(args.delete_source)
        if args.delete_source
        else None
    )
    retriever = PineconeRetriever(
        PineconeConfig(
            api_key=settings.pinecone_api_key,
            index_name=settings.pinecone_index_name,
            namespace=settings.pinecone_namespace,
            embedding_model=settings.pinecone_embedding_model,
            embedding_dimension=settings.pinecone_embedding_dimension,
            timeout_seconds=settings.pinecone_timeout_seconds,
        )
    )
    count = await retriever.upsert_documents(corpus.chunks)
    print(
        f"Indexed {count} synthetic records in namespace "
        f"{settings.pinecone_namespace}."
    )
    if previous_corpus is not None:
        new_ids = {
            PineconeRetriever.vector_id(chunk) for chunk in corpus.chunks
        }
        obsolete_ids = sorted(
            {
                PineconeRetriever.vector_id(chunk)
                for chunk in previous_corpus.chunks
            }
            - new_ids
        )
        deleted = await retriever.delete_documents(obsolete_ids)
        print(
            f"Requested removal of {deleted} prior synthetic records from "
            f"namespace {settings.pinecone_namespace}."
        )


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
