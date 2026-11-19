"""Verify the compiled graph's bounded route and event sequence.

The tests stream node updates and custom lifecycle events directly from the
fixture-backed graph. They check Research ordering, tool execution, and
citation validation.
"""

from datetime import date
from pathlib import Path

import pytest

from enterprise_assistant.agents.graph import build_graph
from enterprise_assistant.agents.state import AgentState
from enterprise_assistant.domain.models import SearchResult
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever
from enterprise_assistant.tools.registry import ToolRegistry


class _CountingRetriever(InMemoryRetriever):
    """Count searches made by the small-talk graph path.

    The counter lets the test distinguish a skipped search from an empty
    search result.
    """

    def __init__(self) -> None:
        """Initialize an empty corpus and zero search count.

        The retriever's result behavior is inherited from the fixture adapter.
        """
        super().__init__([])
        self.search_count = 0

    async def search(
        self,
        query: str,
        *,
        allowed_access_levels: frozenset[str],
        department: str | None = None,
        document_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Count a call before delegating to the empty fixture retriever.

        Args:
            query: Search terms passed by the knowledge tool.
            allowed_access_levels: Trusted access labels for the user role.
            department: Optional backend department restriction.
            document_type: Optional source type restriction.
            date_from: Optional inclusive lower date.
            date_to: Optional inclusive upper date.
            limit: Maximum number of results requested.

        Returns:
            Results returned by the empty in-memory corpus.
        """
        self.search_count += 1
        return await super().search(
            query,
            allowed_access_levels=allowed_access_levels,
            department=department,
            document_type=document_type,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )


@pytest.mark.asyncio
async def test_small_talk_routes_directly_to_response_without_search() -> None:
    """Verify greetings receive a helpful answer without document search.

    The mock supervisor should choose the small-talk route, which skips both
    retrieval and the evidence-based answer provider.
    """
    retriever = _CountingRetriever()
    graph = build_graph(retriever, ToolRegistry())
    state: AgentState = {
        "request_id": "graph-small-talk-test",
        "session_id": "session-small-talk-test",
        "user_id": "viewer",
        "role": "viewer",
        "question": "Hello!",
        "events": [],
    }

    updates = [
        update async for update in graph.astream(state, stream_mode="updates")
    ]
    node_names = [node for update in updates for node in update]

    assert node_names == ["supervisor", "response", "validate"]
    assert updates[0]["supervisor"]["route"] == "small_talk"
    answer = updates[1]["response"]["response"]
    assert answer.startswith("Hello!")
    assert "runbooks" in answer
    assert retriever.search_count == 0
    assert updates[1]["response"]["citations"] == []


@pytest.mark.asyncio
async def test_compiled_graph_routes_nodes_and_emits_typed_events() -> None:
    """Verify the Research route executes its recursive node and emits events.

    The deterministic graph must traverse supervisor, research, response,
    and citation validation in order. Research owns its authorized searches.

    Notes:
        The test uses fixture retrieval and does not contact external
        providers.
    """
    graph = build_graph(
        InMemoryRetriever.from_json(Path("data/samples/incident_corpus.json")),
        ToolRegistry(),
    )
    state: AgentState = {
        "request_id": "graph-test",
        "session_id": "session-test",
        "user_id": "viewer",
        "role": "viewer",
        "question": "Investigate gateway timeout response steps",
        "events": [],
    }
    updates = [
        update async for update in graph.astream(state, stream_mode="updates")
    ]
    node_names = [node for update in updates for node in update]
    assert node_names == ["supervisor", "research", "response", "validate"]
    event_types = [
        event["event_type"]
        for update in updates
        for node in update.values()
        for event in node.get("events", [])
    ]
    assert "retrieval" in event_types
    assert "validation" in event_types
    assert "response_chunk" in event_types
    research_update = updates[1]["research"]
    assert research_update["investigation_summary"]["search_calls"] == 1


@pytest.mark.asyncio
async def test_graph_aggregates_a_multi_subtask_incident_investigation() -> (
    None
):
    """Verify a compound incident question reaches recursive aggregation.

    Mock mode deterministically creates symptoms, cause, and mitigation
    subtasks. The graph executes all three authorized searches and carries
    the attributed findings into its response stage.
    """
    graph = build_graph(
        InMemoryRetriever.from_json(Path("data/samples/incident_corpus.json")),
        ToolRegistry(),
    )
    state: AgentState = {
        "request_id": "graph-rlm-test",
        "session_id": "session-rlm-test",
        "user_id": "viewer",
        "role": "viewer",
        "question": (
            "Investigate payment incidents and compare symptoms, causes, "
            "and mitigations."
        ),
        "events": [],
    }

    updates = [
        update async for update in graph.astream(state, stream_mode="updates")
    ]
    research_update = updates[1]["research"]

    assert research_update["investigation_summary"]["search_calls"] == 3
    assert len(research_update["investigation_findings"]) == 3
    assert research_update["results"]
    assert all(
        finding["sources"]
        for finding in research_update["investigation_findings"]
    )


@pytest.mark.asyncio
async def test_graph_analyzes_only_authorized_incidents_with_date_scope() -> (
    None
):
    """Verify research applies an inclusive date range and cause analysis.

    The analyst sees authorized incidents from the injected rolling window.
    """
    graph = build_graph(
        InMemoryRetriever.from_json(Path("data/samples/incident_corpus.json")),
        ToolRegistry(),
        today=lambda: date(2026, 11, 15),
    )
    state: AgentState = {
        "request_id": "graph-incident-analysis",
        "session_id": "session-incident-analysis",
        "user_id": "analyst",
        "role": "analyst",
        "question": (
            "Summarize payment outages during the last year and "
            "identify recurring root causes."
        ),
        "events": [],
    }

    updates = [
        update async for update in graph.astream(state, stream_mode="updates")
    ]
    research = updates[1]["research"]
    summary = research["incident_analysis_result"]
    returned = research["results"]

    assert updates[0]["supervisor"]["route"] == "research"
    assert research["investigation_summary"]["search_calls"] >= 2
    assert research["investigation_summary"]["subtask_count"] >= 2
    assert research["investigation_summary"]["batch_count"] >= 1
    assert summary["incidents_analyzed"] >= 2
    assert summary["date_from"] == "2025-11-15"
    assert summary["date_to"] == "2026-11-15"
    assert all(
        item["chunk"]["metadata"]["access_level"] in {"viewer", "analyst"}
        for item in returned
    )
    assert all(
        "2025-11-14" < item["chunk"]["metadata"]["created_date"] <= "2026-11-15"
        for item in returned
    )
    assert updates[3]["validate"]["validation_passed"] is True
    assert "unique incident(s)" in updates[2]["response"]["response"]


@pytest.mark.asyncio
async def test_viewer_is_denied_incident_analysis_before_retrieval() -> None:
    """Deny incident analysis before starting any search.

    The test retriever counts calls to prove authorization happens first.
    """

    class CountingRetriever(InMemoryRetriever):
        """Track calls to prove authorization precedes retrieval.

        The wrapper keeps the synthetic assessment records available.
        """

        def __init__(self) -> None:
            """Create a counting wrapper around the incident fixture.

            The inherited adapter applies the ordinary local filters.
            """
            super().__init__(
                list(
                    InMemoryRetriever.from_json(
                        Path("data/samples/incident_corpus.json")
                    ).chunks
                )
            )
            self.search_count = 0

        async def search(self, query: str, **kwargs: object):
            """Count calls before delegating to fixture retrieval.

            Args:
                query: Search terms supplied by the graph.
                kwargs: Trusted scope and result-limit arguments.

            Returns:
                Matching source chunks from the fixture corpus.
            """
            self.search_count += 1
            return await super().search(query, **kwargs)

    retriever = CountingRetriever()
    graph = build_graph(retriever, ToolRegistry())
    state: AgentState = {
        "request_id": "graph-viewer-analysis",
        "session_id": "session-viewer-analysis",
        "user_id": "viewer",
        "role": "viewer",
        "question": (
            "Summarize payment outages during the last year and "
            "identify recurring root causes."
        ),
        "events": [],
    }

    updates = [
        update async for update in graph.astream(state, stream_mode="updates")
    ]

    assert updates[1]["research"]["analysis_error"] == (
        "incident_analysis_forbidden"
    )
    assert updates[2]["response"]["response"].startswith(
        "This account is not authorized"
    )
    assert retriever.search_count == 0


@pytest.mark.asyncio
async def test_analysis_route_executes_tool_only_for_authorized_roles() -> None:
    """Verify explicit arithmetic uses the tool registry's role policy.

    Analysts receive a computed result. Viewers reach the same route but are
    rejected by server-side policy before the Python handler can run.
    """
    graph = build_graph(InMemoryRetriever([]), ToolRegistry())

    async def run_as(role: str) -> list[dict[str, object]]:
        """Run one arithmetic request as a fixed authenticated role.

        Args:
            role: Server-assigned test role, never request data.

        Returns:
            LangGraph updates for the requested conversation.
        """
        state: AgentState = {
            "request_id": f"analysis-{role}",
            "session_id": f"analysis-session-{role}",
            "user_id": role,
            "role": role,
            "question": "Calculate average of 10, 20, 30.",
            "events": [],
        }
        return [
            part
            async for part in graph.astream(
                state,
                stream_mode=["updates", "custom"],
                version="v2",
            )
        ]

    analyst_parts = await run_as("analyst")
    viewer_parts = await run_as("viewer")
    analyst_updates = [
        part["data"] for part in analyst_parts if part["type"] == "updates"
    ]
    viewer_updates = [
        part["data"] for part in viewer_parts if part["type"] == "updates"
    ]
    analyst_events = [
        part["data"] for part in analyst_parts if part["type"] == "custom"
    ]
    analyst_response = analyst_updates[2]["response"]
    viewer_response = viewer_updates[2]["response"]
    viewer_analysis = viewer_updates[1]["analysis"]

    assert analyst_updates[0]["supervisor"]["route"] == "analysis"
    assert "20" in analyst_response["response"]
    assert (
        analyst_updates[1]["analysis"]["analysis_result"]["operation"]
        == "average"
    )
    assert [event["event_type"] for event in analyst_events] == [
        "agent_start",
        "agent_complete",
        "agent_start",
        "tool_start",
        "tool_complete",
        "agent_complete",
        "agent_start",
        "agent_complete",
        "agent_start",
        "agent_complete",
    ]
    assert "not authorized" in viewer_response["response"]
    assert viewer_analysis["analysis_error"] == "python_analysis_forbidden"
