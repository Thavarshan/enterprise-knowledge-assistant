"""Index configured synthetic assessment chunks in an existing namespace.

The command reads the configured chunk corpus and upserts stable IDs through
Pinecone's schema-aware Documents API. The existing index schema performs
embedding. The command never creates an index or logs credentials or content.
"""

import asyncio
from pathlib import Path

from enterprise_assistant.config.settings import get_settings
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever
from enterprise_assistant.retrieval.pinecone import (
    PineconeConfig,
    PineconeRetriever,
)


async def main() -> None:
    """Ingest the validated source corpus into the configured namespace.

    Raises:
        PineconeNotConfigured: Required Pinecone settings are absent.
        PineconeRequestError: Indexing or embedding fails.
    """
    settings = get_settings()
    corpus = InMemoryRetriever.from_json(Path(settings.pinecone_documents_path))
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
        f"Indexed {count} synthetic chunks in namespace "
        f"{settings.pinecone_namespace}."
    )


if __name__ == "__main__":
    asyncio.run(main())
