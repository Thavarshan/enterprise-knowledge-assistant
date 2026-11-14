"""Ingest and search documents in an existing Pinecone schema index.

This adapter uses the Documents API because the configured index was created
with a document schema. Its `chunk_text` field has Pinecone-hosted dense
embeddings and full-text search; separate query modes feed the existing RRF
hybrid ranker. It never creates or alters indexes.
"""

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pinecone import EmbedQuery, Pinecone, RetryConfig, TextQuery

from enterprise_assistant.domain.models import (
    DocumentChunk,
    DocumentMetadata,
    SearchResult,
)

logger = logging.getLogger(__name__)

_CONTENT_FIELD = "chunk_text"
_TITLE_FIELD = "title"
_ATTRIBUTION_FIELDS = (
    "document_id",
    "chunk_id",
    "department",
    "document_type",
    "access_level",
    "created_date",
    "source",
)
_SEARCH_FIELDS = (_CONTENT_FIELD, _TITLE_FIELD, *_ATTRIBUTION_FIELDS)


class PineconeNotConfigured(RuntimeError):
    """Report missing Pinecone index, namespace, or credentials.

    This configuration error is raised without including the secret value.
    """


class PineconeRequestError(RuntimeError):
    """Report a sanitized Pinecone request or schema compatibility failure.

    Provider exception text is not included because it may contain request
    details or service data.
    """


@dataclass(frozen=True)
class PineconeConfig:
    """Hold settings for the existing Pinecone document index.

    Attributes:
        api_key: Pinecone API key hidden from generated representations.
        index_name: Existing index name; this adapter never creates indexes.
        namespace: Explicit namespace for isolated assessment documents.
        embedding_model: Dense model already declared in the index schema.
        embedding_dimension: Dense dimension declared in that schema.
        timeout_seconds: End-to-end timeout for one SDK operation.
    """

    api_key: str = field(repr=False)
    index_name: str
    namespace: str
    embedding_model: str = "llama-text-embed-v2"
    embedding_dimension: int = 1024
    timeout_seconds: int = 15


class PineconeRetriever:
    """Embed, ingest, and search chunks in a filtered document namespace.

    The SDK is synchronous, so network calls run in worker threads. SDK HTTP
    deadlines, disabled retries, and an enclosing async timeout bound each
    operation. Dense and full-text BM25 methods share the same filtered index.

    Attributes:
        config: Index and model settings with a hidden API key.
    """

    def __init__(
        self,
        config: PineconeConfig,
        *,
        client: Any | None = None,
    ) -> None:
        """Store settings and create a lazy Pinecone client.

        Args:
            config: Existing index settings and namespace.
            client: Optional SDK-compatible client used by tests.
        """
        self.config = config
        self._client = client
        if self._client is None and config.api_key.strip():
            self._client = Pinecone(
                api_key=config.api_key,
                timeout=float(config.timeout_seconds),
                retry_config=RetryConfig(max_retries=0),
            )
        self._index: Any | None = None
        self._connect_lock = asyncio.Lock()

    async def upsert_documents(
        self,
        chunks: Sequence[DocumentChunk],
        *,
        batch_size: int = 32,
    ) -> int:
        """Upsert stable source identities using the Documents API.

        The schema embeds the `chunk_text` field during ingestion. Repeated
        ingestion uses deterministic IDs, updating existing synthetic chunks
        rather than adding duplicates.

        Args:
            chunks: Validated source chunks to index.
            batch_size: Maximum documents sent in one request.

        Returns:
            Number of documents accepted by Pinecone.

        Raises:
            ValueError: Batch size is invalid or source identities repeat.
            PineconeNotConfigured: Required connection settings are absent.
            PineconeRequestError: A request or schema check fails.
        """
        if not 1 <= batch_size <= 96:
            raise ValueError("batch_size must be between 1 and 96")
        documents = tuple(chunks)
        identities = [
            (chunk.metadata.document_id, chunk.metadata.chunk_id)
            for chunk in documents
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("Document and chunk identities must be unique.")
        for chunk in documents:
            self._validate_metadata_size(chunk)
        if not documents:
            return 0

        self._require_configuration()
        try:
            async with asyncio.timeout(self.config.timeout_seconds):
                index = await self._ensure_index()
                for offset in range(0, len(documents), batch_size):
                    batch = documents[offset:offset + batch_size]
                    await asyncio.to_thread(
                        self._upsert_batch,
                        index,
                        batch,
                    )
        except asyncio.CancelledError:
            raise
        except TimeoutError as exc:
            raise PineconeRequestError(
                "Pinecone document ingestion timed out."
            ) from exc
        except (PineconeNotConfigured, PineconeRequestError):
            raise
        except Exception as exc:
            logger.warning(
                "Pinecone document ingestion failed",
                extra={"error_type": type(exc).__name__},
            )
            raise PineconeRequestError(
                "Pinecone document ingestion failed."
            ) from exc
        return len(documents)

    async def search(
        self,
        query: str,
        *,
        allowed_access_levels: frozenset[str],
        department: str | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Return dense semantic results under Pinecone metadata filters.

        Args:
            query: Natural-language request to embed through the index schema.
            allowed_access_levels: Trusted role-derived access labels.
            department: Optional trusted exact department constraint.
            limit: Maximum number of matches to convert.

        Returns:
            Dense-ranked authorized results with validated provenance.

        Raises:
            PineconeNotConfigured: Required connection settings are absent.
            PineconeRequestError: A provider request or response fails.
        """
        return await self._search(
            query,
            allowed_access_levels=allowed_access_levels,
            department=department,
            limit=limit,
            scoring=EmbedQuery(field=_CONTENT_FIELD, query=query),
        )

    async def search_sparse(
        self,
        query: str,
        *,
        allowed_access_levels: frozenset[str],
        department: str | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Return full-text BM25 results under the same metadata filters.

        Args:
            query: Natural-language or exact identifier search text.
            allowed_access_levels: Trusted role-derived access labels.
            department: Optional trusted exact department constraint.
            limit: Maximum number of matches to convert.

        Returns:
            BM25-ranked authorized results with validated provenance.
        """
        return await self._search(
            query,
            allowed_access_levels=allowed_access_levels,
            department=department,
            limit=limit,
            scoring=TextQuery(fields=[_CONTENT_FIELD], query=query),
        )

    async def _search(
        self,
        query: str,
        *,
        allowed_access_levels: frozenset[str],
        department: str | None,
        limit: int,
        scoring: Any,
    ) -> list[SearchResult]:
        """Execute one filtered dense or BM25 document query.

        Args:
            query: Query text used by the selected index scoring clause.
            allowed_access_levels: Backend-derived readable labels.
            department: Optional trusted department constraint.
            limit: Maximum number of result matches.
            scoring: Pinecone EmbedQuery or TextQuery object.

        Returns:
            Results rechecked against the trusted filters.
        """
        if limit <= 0 or not allowed_access_levels:
            return []
        self._require_configuration()
        try:
            async with asyncio.timeout(self.config.timeout_seconds):
                index = await self._ensure_index()
                return await asyncio.to_thread(
                    self._search_documents,
                    index,
                    query,
                    allowed_access_levels,
                    department,
                    limit,
                    scoring,
                )
        except asyncio.CancelledError:
            raise
        except TimeoutError as exc:
            raise PineconeRequestError("Pinecone search timed out.") from exc
        except (PineconeNotConfigured, PineconeRequestError):
            raise
        except Exception as exc:
            logger.warning(
                "Pinecone search failed",
                extra={"error_type": type(exc).__name__},
            )
            raise PineconeRequestError("Pinecone search failed.") from exc

    def _require_configuration(self) -> None:
        """Reject missing credentials and explicit index scope values.

        Raises:
            PineconeNotConfigured: A required setting is blank.
        """
        if (
            self._client is None
            or not self.config.index_name.strip()
            or not self.config.namespace.strip()
        ):
            raise PineconeNotConfigured(
                "Set Pinecone credentials, index, and namespace."
            )

    async def _ensure_index(self) -> Any:
        """Lazily describe and validate the existing document schema.

        Returns:
            A cached SDK index handle pointed at the described host.

        Raises:
            PineconeRequestError: The index is unavailable or incompatible.
        """
        async with self._connect_lock:
            cached_index = self._index
            if cached_index is not None:
                return cached_index
            try:
                index = await asyncio.to_thread(self._connect_index)
            except PineconeNotConfigured:
                raise
            except Exception as exc:
                logger.warning(
                    "Pinecone index inspection failed",
                    extra={"error_type": type(exc).__name__},
                )
                raise PineconeRequestError(
                    "The configured Pinecone index is unavailable."
                ) from exc
            self._index = index
            return index

    def _connect_index(self) -> Any:
        """Validate schema fields and return the existing index handle.

        Returns:
            SDK index handle using the host returned by Pinecone.

        Raises:
            PineconeNotConfigured: The Pinecone client was not initialized.
            PineconeRequestError: The index lacks required schema fields.
        """
        client = self._client
        if client is None:
            raise PineconeNotConfigured(
                "Set Pinecone credentials, index, and namespace."
            )
        description = client.describe_index(self.config.index_name)
        status = getattr(description, "status", None)
        if status is not None and not getattr(status, "ready", True):
            raise PineconeRequestError(
                "The configured Pinecone index is not ready."
            )
        schema = getattr(description, "schema", None)
        fields = getattr(schema, "fields", {}) if schema is not None else {}
        content_definition = fields.get(_CONTENT_FIELD)
        title_definition = fields.get(_TITLE_FIELD)
        embedding = getattr(content_definition, "embed", None)
        full_text = getattr(content_definition, "full_text_search", None)
        host = getattr(description, "host", None)
        if (
            not host
            or embedding is None
            or full_text is None
            or title_definition is None
            or getattr(embedding, "model", None)
            != self.config.embedding_model
            or getattr(embedding, "dimension", None)
            != self.config.embedding_dimension
        ):
            raise PineconeRequestError(
                "The configured index schema does not match this adapter."
            )
        return client.Index(host=host)

    def _upsert_batch(
        self,
        index: Any,
        chunks: Sequence[DocumentChunk],
    ) -> None:
        """Upsert source records through the document-schema endpoint.

        Args:
            index: SDK handle for the validated existing index.
            chunks: Batch of validated source chunks.
        """
        index.documents.upsert(
            namespace=self.config.namespace,
            documents=[self._document(chunk) for chunk in chunks],
            timeout=float(self.config.timeout_seconds),
        )

    def _search_documents(
        self,
        index: Any,
        query: str,
        allowed_access_levels: frozenset[str],
        department: str | None,
        limit: int,
        scoring: Any,
    ) -> list[SearchResult]:
        """Search documents and recheck metadata before reading text.

        Args:
            index: SDK handle for the validated existing index.
            query: Untrusted query string.
            allowed_access_levels: Trusted role-derived access labels.
            department: Optional trusted department constraint.
            limit: Maximum number of matches to convert.
            scoring: Dense or full-text scoring clause.

        Returns:
            Ranked results whose metadata passes local scope checks.
        """
        del query
        response = index.documents.search(
            namespace=self.config.namespace,
            top_k=limit,
            score_by=[scoring],
            filter=self._metadata_filter(
                allowed_access_levels,
                department,
            ),
            include_fields=list(_SEARCH_FIELDS),
            timeout=float(self.config.timeout_seconds),
        )
        results: list[SearchResult] = []
        for match in response.matches:
            values = {
                name: getattr(match, name, None)
                for name in _SEARCH_FIELDS
            }
            if values.get("access_level") not in allowed_access_levels:
                continue
            if (
                department is not None
                and values.get("department") != department
            ):
                continue
            content = values.pop(_CONTENT_FIELD, None)
            if not isinstance(content, str) or not content:
                continue
            metadata = DocumentMetadata.model_validate(values)
            chunk = DocumentChunk(content=content, metadata=metadata)
            score = max(0.0, float(getattr(match, "score", 0.0) or 0.0))
            results.append(
                SearchResult(
                    chunk=chunk,
                    score=score,
                    rank=len(results) + 1,
                )
            )
        return results

    @staticmethod
    def _document(chunk: DocumentChunk) -> dict[str, Any]:
        """Map validated chunk fields to the existing document schema.

        Args:
            chunk: Source chunk to ingest with stable metadata.

        Returns:
            Document record with `_id`, `chunk_text`, title, and filters.
        """
        metadata = chunk.metadata.model_dump(mode="json")
        document = {
            "_id": PineconeRetriever.vector_id(chunk),
            _CONTENT_FIELD: chunk.content,
            _TITLE_FIELD: metadata.pop("title"),
        }
        document.update(metadata)
        return document

    @staticmethod
    def vector_id(chunk: DocumentChunk) -> str:
        """Build a stable Pinecone ID from document and chunk identity.

        Args:
            chunk: Validated chunk with stable provenance IDs.

        Returns:
            Deterministic ID unique to the complete source identity.
        """
        return (
            f"{chunk.metadata.document_id}::"
            f"{chunk.metadata.chunk_id}"
        )

    @staticmethod
    def _metadata_filter(
        allowed_access_levels: frozenset[str],
        department: str | None,
    ) -> dict[str, Any]:
        """Create provider-side authorization and department filters.

        Args:
            allowed_access_levels: Backend-derived allowed labels.
            department: Optional trusted exact department constraint.

        Returns:
            Pinecone filter expression applied before fields are returned.
        """
        metadata_filter: dict[str, Any] = {
            "access_level": {"$in": sorted(allowed_access_levels)}
        }
        if department is not None:
            metadata_filter["department"] = {"$eq": department}
        return metadata_filter

    @staticmethod
    def _validate_metadata_size(chunk: DocumentChunk) -> None:
        """Reject chunks that exceed a conservative field-size budget.

        Args:
            chunk: Source chunk whose content will be stored in the index.

        Raises:
            ValueError: Encoded content exceeds the supported chunk budget.
        """
        if len(chunk.content.encode("utf-8")) > 30_000:
            raise ValueError(
                "Chunk content exceeds the Pinecone metadata limit."
            )
