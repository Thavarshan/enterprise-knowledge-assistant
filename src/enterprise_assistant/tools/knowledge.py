"""Apply role-derived access and validated source filters to retrieval.

The tool converts the authenticated role into allowed access levels and
forwards optional source filters parsed from the original question. It is
the graph's executable search tool and receives identity only from trusted
graph state.
"""

from collections.abc import Callable
from datetime import date
from typing import Any

from langsmith import traceable

from enterprise_assistant.domain.models import SearchResult
from enterprise_assistant.retrieval.filters import (
    filters_for_question,
    incident_ids_in_question,
)
from enterprise_assistant.retrieval.interfaces import Retriever
from enterprise_assistant.security.authorization import (
    Role,
    allowed_access_levels,
)


class KnowledgeSearchTool:
    """Apply role-derived access restrictions to retrieval.

    The graph invokes this tool only after ToolRegistry authorizes the
    knowledge-search policy. It converts the role to allowed access labels,
    forwards source filters, and narrows explicit incident IDs to exact
    matching records.

    Attributes:
        retriever: Adapter receiving the search and trusted filters.
    """

    def __init__(
        self,
        retriever: Retriever,
        *,
        today: Callable[[], date] = date.today,
    ) -> None:
        """Retain the search adapter used by this tool.

        Args:
            retriever: Implementation of the shared retrieval protocol.
            today: Injectable clock used to resolve relative date phrases.
        """
        self.retriever = retriever
        self.today = today

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
            Authorized results restricted to explicitly named incidents,
            when the question names any.

        Raises:
            KeyError: Required query or role fields are absent.
            ValueError: Role or integer limit cannot be parsed.
            Exception: Adapter failures propagate to graph error handling.
        """
        role = Role(arguments["role"])
        query = str(arguments["query"])
        filter_question = str(arguments.get("filter_question", query))
        incident_ids = incident_ids_in_question(filter_question)
        filters = filters_for_question(
            filter_question,
            today=self.today(),
            department=arguments.get("department"),
        )
        # Derive scope from the authenticated role, never from a requested
        # access-level argument, before content crosses into graph state.
        results = list(
            await self.retriever.search(
                query,
                allowed_access_levels=allowed_access_levels(role),
                department=filters.department,
                document_type=filters.document_type,
                date_from=filters.date_from,
                date_to=filters.date_to,
                limit=int(arguments.get("limit", 5)),
            )
        )
        if not incident_ids:
            return results

        matching_results = [
            result
            for result in results
            if (result.chunk.metadata.incident_id or "").upper() in incident_ids
        ]
        return matching_results
