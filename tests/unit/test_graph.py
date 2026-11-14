"""Verify the compiled graph's bounded route and event sequence.

The test streams node updates directly from the fixture-backed graph and
checks that Research executes before response and citation validation.
"""

from pathlib import Path

import pytest

from enterprise_assistant.agents.graph import build_graph
from enterprise_assistant.agents.state import AgentState
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever
from enterprise_assistant.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_compiled_graph_executes_routed_nodes_and_emits_typed_events(
) -> None:
    """Verify the Research route executes its recursive node and emits events.

    The deterministic graph must traverse supervisor, research, response,
    and citation validation in order. Research owns its authorized searches.

    Notes:
        The test uses fixture retrieval and does not contact external
        providers.
    """
    graph = build_graph(
        InMemoryRetriever.from_json(
            Path("data/samples/incident_corpus.json")
        ),
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
async def test_graph_aggregates_a_multi_subtask_incident_investigation(
) -> None:
    """Verify a compound incident question reaches recursive aggregation.

    Mock mode deterministically creates symptoms, cause, and mitigation
    subtasks. The graph executes all three authorized searches and carries
    the attributed findings into its response stage.
    """
    graph = build_graph(InMemoryRetriever.from_json(), ToolRegistry())
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
