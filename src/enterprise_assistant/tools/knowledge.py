"""Apply role-derived access filters before calling a retriever.

The tool converts the authenticated role into allowed access levels and
forwards query, optional department, and result limit. It is the graph's
current executable tool and must receive identity from trusted graph state.
"""

from typing import Any

from langsmith import traceable

from enterprise_assistant.domain.models import SearchResult
from enterprise_assistant.retrieval.interfaces import Retriever
from enterprise_assistant.security.authorization import Role


def allowed_access_levels(role: Role) -> frozenset[str]:
    """Map the authenticated role to searchable access labels.

    Viewer results include viewer-level material; analysts also include
    analyst material; administrators include all three labels.

    Args:
        role: Server-resolved role from authenticated graph state.

    Returns:
        Immutable set of access labels for the retrieval filter.
    """
    return {
        Role.VIEWER: frozenset({"viewer"}),
        Role.ANALYST: frozenset({"viewer", "analyst"}),
        Role.ADMINISTRATOR: frozenset({"viewer", "analyst", "administrator"}),
    }[role]


class KnowledgeSearchTool:
    """Apply role-derived access restrictions to retrieval.

    The graph invokes this tool only after ToolRegistry authorizes the
    knowledge-search policy. It converts the role to allowed access labels
    and forwards filters to the injected retriever.

    Attributes:
        retriever: Adapter receiving the search and trusted filters.
    """

    def __init__(self, retriever: Retriever) -> None:
        """Retain the search adapter used by this tool.

        Args:
            retriever: Implementation of the shared retrieval protocol.
        """
        self.retriever = retriever

    @traceable(
        name="knowledge_search",
        run_type="tool",
        metadata={"tool_name": "knowledge_search"},
    )
    async def run(self, arguments: dict[str, Any]) -> list[SearchResult]:
        """Search for chunks after deriving access labels from the role.

        The handler expects role and query fields from trusted graph state.
        It does not accept arbitrary access levels from callers.

        LangSmith context propagation makes this tool a child of the retrieval
        node. The configured client hides arguments and retrieved content.

        Args:
            arguments: Tool input containing query, role, and optional
                department and result limit.

        Returns:
            Retrieved result objects from the configured adapter.

        Raises:
            KeyError: Required query or role fields are absent.
            ValueError: Role or integer limit cannot be parsed.
            Exception: Adapter failures propagate to graph error handling.
        """
        role = Role(arguments["role"])
        # Derive scope from the authenticated role, never from a requested
        # access-level argument, before content crosses into graph state.
        return list(
            await self.retriever.search(
                str(arguments["query"]),
                allowed_access_levels=allowed_access_levels(role),
                department=arguments.get("department"),
                limit=int(arguments.get("limit", 5)),
            )
        )
