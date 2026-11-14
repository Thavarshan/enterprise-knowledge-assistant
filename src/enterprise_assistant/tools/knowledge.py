"""Role-filtered knowledge search tool used by the graph's retrieval node."""

from typing import Any

from enterprise_assistant.domain.models import SearchResult
from enterprise_assistant.retrieval.interfaces import Retriever
from enterprise_assistant.security.authorization import Role


def allowed_access_levels(role: Role) -> frozenset[str]:
    return {
        Role.VIEWER: frozenset({"viewer"}),
        Role.ANALYST: frozenset({"viewer", "analyst"}),
        Role.ADMINISTRATOR: frozenset({"viewer", "analyst", "administrator"}),
    }[role]


class KnowledgeSearchTool:
    def __init__(self, retriever: Retriever) -> None:
        self.retriever = retriever

    async def run(self, arguments: dict[str, Any]) -> list[SearchResult]:
        role = Role(arguments["role"])
        return list(
            await self.retriever.search(
                str(arguments["query"]),
                allowed_access_levels=allowed_access_levels(role),
                department=arguments.get("department"),
                limit=int(arguments.get("limit", 5)),
            )
        )
