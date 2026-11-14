"""Pinecone configuration boundary; live indexing and querying are deferred."""

from dataclasses import dataclass

from enterprise_assistant.domain.models import SearchResult


class PineconeNotConfigured(RuntimeError):
    """Raised until the production Pinecone client and index are wired in."""


@dataclass(frozen=True)
class PineconeConfig:
    api_key: str
    index_name: str
    namespace: str = ""


class PineconeRetriever:
    """Explicit adapter seam that never silently swaps in another vector DB."""

    def __init__(self, config: PineconeConfig) -> None:
        self.config = config

    async def search(
        self,
        query: str,
        *,
        allowed_access_levels: frozenset[str],
        department: str | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        del query, allowed_access_levels, department, limit
        raise PineconeNotConfigured(
            "Pinecone query execution is scaffolded; configure the production adapter first."
        )
