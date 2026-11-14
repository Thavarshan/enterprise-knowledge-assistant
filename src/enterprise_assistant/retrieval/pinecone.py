"""Expose configuration and an explicit, not-yet-wired Pinecone boundary.

The API factory selects this adapter when mock mode is disabled, but
`search` raises `PineconeNotConfigured`; no SDK client, index call, ingestion,
metadata filter, or fallback provider is implemented here.
"""

from dataclasses import dataclass

from enterprise_assistant.domain.models import SearchResult


class PineconeNotConfigured(RuntimeError):
    """Signal that the production Pinecone adapter is unavailable.

    The configured non-mock path selects PineconeRetriever, whose current
    search method raises this error instead of returning fabricated data.
    """


@dataclass(frozen=True)
class PineconeConfig:
    """Hold the values needed to configure a Pinecone index adapter.

    This frozen configuration is currently a scaffold. No SDK client
    consumes it, and api_key must be treated as secret if the integration is
    implemented.

    Attributes:
        api_key: Secret credential for a future provider client.
        index_name: Target index name.
        namespace: Optional tenant or collection namespace.

    Security:
        The default dataclass representation includes api_key. Do not log
        or format this configuration object.
    """
    api_key: str
    index_name: str
    namespace: str = ""


class PineconeRetriever:
    """Expose the explicit but unimplemented Pinecone search boundary.

    The API selects this adapter when mock mode is disabled. Search currently
    raises PineconeNotConfigured; it does not connect, filter metadata,
    execute a query, or fall back to fixture search.

    Attributes:
        config: Index and credential settings retained by the scaffold.
    """

    def __init__(self, config: PineconeConfig) -> None:
        """Retain the provider configuration for this adapter.

        Args:
            config: Pinecone index settings; no SDK client is created.
        """
        self.config = config

    async def search(
        self,
        query: str,
        *,
        allowed_access_levels: frozenset[str],
        department: str | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Fail explicitly until Pinecone query execution is implemented.

        The arguments satisfy the shared Retriever protocol but are not
        consumed. This prevents the non-mock mode from silently returning
        local fixture results.

        Args:
            query: Search text; currently unused.
            allowed_access_levels: Trusted labels required by the contract.
            department: Optional trusted department restriction.
            limit: Requested maximum results.

        Raises:
            PineconeNotConfigured: The adapter has no SDK client or query
                implementation.
        """
        del query, allowed_access_levels, department, limit
        raise PineconeNotConfigured(
            "Pinecone query execution is scaffolded; configure the production "
            "adapter first."
        )
