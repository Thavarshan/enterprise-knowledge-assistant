"""Directly exercise the compiled LangGraph state transitions."""

import pytest

from enterprise_assistant.agents.graph import build_graph
from enterprise_assistant.agents.state import AgentState
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever
from enterprise_assistant.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_compiled_graph_executes_routed_nodes_and_emits_typed_events() -> None:
    graph = build_graph(InMemoryRetriever.from_json(), ToolRegistry())
    state: AgentState = {
        "request_id": "graph-test",
        "session_id": "session-test",
        "user_id": "viewer",
        "role": "viewer",
        "question": "Investigate gateway timeout response steps",
        "events": [],
    }
    updates = [update async for update in graph.astream(state, stream_mode="updates")]
    node_names = [node for update in updates for node in update]
    assert node_names == ["supervisor", "research", "retrieval", "response", "validate"]
    event_types = [
        event["event_type"]
        for update in updates
        for node in update.values()
        for event in node.get("events", [])
    ]
    assert "retrieval" in event_types
    assert "validation" in event_types
    assert "response_chunk" in event_types
