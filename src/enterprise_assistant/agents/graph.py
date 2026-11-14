"""Small compiled LangGraph workflow with real, streamed state transitions."""

import re
from collections.abc import AsyncIterator
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from enterprise_assistant.agents.state import AgentState
from enterprise_assistant.domain.models import SearchResult, SourceCitation
from enterprise_assistant.observability.events import ActivityEvent, EventType
from enterprise_assistant.retrieval.interfaces import Retriever
from enterprise_assistant.rlm.contracts import ExecutionBudget, interpret_search_plan, plan_queries
from enterprise_assistant.security.authorization import Role
from enterprise_assistant.tools.knowledge import KnowledgeSearchTool
from enterprise_assistant.tools.registry import ToolRegistry

_CITATION_PATTERN = re.compile(r"\[([a-zA-Z0-9_-]+#[a-zA-Z0-9_-]+)\]")


def _event(
    state: AgentState,
    *,
    event_type: EventType,
    agent: str,
    node: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return ActivityEvent(
        event_type=event_type,
        request_id=state["request_id"],
        session_id=state["session_id"],
        agent=agent,
        node=node,
        message=message,
        metadata=metadata or {},
    ).model_dump(mode="json")


def validate_citations(
    response: str,
    citations: list[SourceCitation],
    retrieved_chunk_ids: frozenset[str],
) -> bool:
    """Require every response citation to identify evidence retrieved this turn."""
    markers = set(_CITATION_PATTERN.findall(response))
    allowed_markers = {
        f"{citation.document_id}#{citation.chunk_id}"
        for citation in citations
        if citation.chunk_id in retrieved_chunk_ids
    }
    if not markers:
        return not citations
    return markers == allowed_markers


def build_graph(retriever: Retriever, tool_registry: ToolRegistry) -> Any:
    """Compile the deterministic workflow; a checkpointer can be supplied later."""

    async def supervisor(state: AgentState) -> dict[str, Any]:
        question = state["question"].casefold()
        route = (
            "research"
            if any(word in question for word in ("investigate", "compare", "analyze"))
            else "retrieval"
        )
        event = _event(
            state,
            event_type="agent_transition",
            agent="supervisor",
            node="supervisor",
            message=f"Selected the {route} workflow.",
            metadata={"decision": route},
        )
        return {"route": route, "events": [event]}

    async def research(state: AgentState) -> dict[str, Any]:
        plan = plan_queries(state["question"], max_queries=1)
        budget = ExecutionBudget(max_depth=1, max_search_calls=1, max_documents=5)
        queries = interpret_search_plan(plan, budget)
        event = _event(
            state,
            event_type="agent_transition",
            agent="research",
            node="research",
            message="Prepared a bounded structured search plan.",
            metadata={"query_count": len(queries), "max_depth": budget.max_depth},
        )
        return {
            "search_plan": {"queries": list(queries), "max_depth": plan.max_depth},
            "events": [event],
        }

    knowledge_search = KnowledgeSearchTool(retriever)

    async def retrieval(state: AgentState) -> dict[str, Any]:
        role = Role(state["role"])
        plan = state.get("search_plan", {"queries": [state["question"]]})
        query = cast(list[str], plan["queries"])[0]
        results = await tool_registry.execute(
            "knowledge_search",
            role,
            {"query": query, "role": role.value, "limit": ExecutionBudget().max_documents},
            {"knowledge_search": knowledge_search.run},
        )
        serialized = [result.model_dump(mode="json") for result in results]
        source_list = [
            {
                "document_id": result.chunk.metadata.document_id,
                "chunk_id": result.chunk.metadata.chunk_id,
                "title": result.chunk.metadata.title,
                "score": result.score,
            }
            for result in results
        ]
        events = [
            _event(
                state,
                event_type="tool_execution",
                agent="retrieval",
                node="retrieval",
                message="Knowledge search completed.",
                metadata={"tool": "knowledge_search", "result_count": len(results)},
            ),
            _event(
                state,
                event_type="retrieval",
                agent="retrieval",
                node="retrieval",
                message=f"Found {len(results)} accessible source chunk(s).",
                metadata={"sources": source_list},
            ),
        ]
        return {"results": serialized, "events": events}

    async def response(state: AgentState) -> dict[str, Any]:
        results = [SearchResult.model_validate(result) for result in state.get("results", [])]
        if results:
            citations = [SourceCitation.from_chunk(result.chunk) for result in results[:2]]
            answer = "\n\n".join(
                f"{result.chunk.content} [{citation.document_id}#{citation.chunk_id}]"
                for result, citation in zip(results[:2], citations, strict=True)
            )
        else:
            citations = []
            answer = "I could not find an accessible document that answers this question."
        events = [
            _event(
                state,
                event_type="agent_transition",
                agent="response",
                node="response",
                message="Prepared a response grounded in retrieved fixture evidence.",
                metadata={"citation_count": len(citations)},
            )
        ]
        return {
            "response": answer,
            "citations": [citation.model_dump() for citation in citations],
            "events": events,
        }

    async def validate(state: AgentState) -> dict[str, Any]:
        citations = [
            SourceCitation.model_validate(citation) for citation in state.get("citations", [])
        ]
        retrieved_ids = frozenset(
            SearchResult.model_validate(result).chunk.metadata.chunk_id
            for result in state.get("results", [])
        )
        valid = validate_citations(state.get("response", ""), citations, retrieved_ids)
        answer = state.get("response", "")
        if not valid:
            answer = "I could not return a response because its source citations did not validate."
            citations = []
        event = _event(
            state,
            event_type="validation",
            agent="response",
            node="validate",
            message="Citation references validated." if valid else "Citation validation failed.",
            metadata={"valid": valid, "citation_count": len(citations)},
        )
        events = [event]
        if valid:
            events.extend(
                _event(
                    state,
                    event_type="response_chunk",
                    agent="response",
                    node="validate",
                    message=answer[start : start + 80],
                )
                for start in range(0, len(answer), 80)
            )
        else:
            events.append(
                _event(
                    state,
                    event_type="failure",
                    agent="response",
                    node="validate",
                    message="The response was withheld because its citations did not validate.",
                    metadata={"error_code": "citation_validation_failed"},
                )
            )
        return {
            "response": answer,
            "citations": [citation.model_dump() for citation in citations],
            "validation_passed": valid,
            "events": events,
        }

    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor)
    graph.add_node("research", research)
    graph.add_node("retrieval", retrieval)
    graph.add_node("response", response)
    graph.add_node("validate", validate)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        lambda state: state["route"],
        {"retrieval": "retrieval", "research": "research"},
    )
    graph.add_edge("research", "retrieval")
    graph.add_edge("retrieval", "response")
    graph.add_edge("response", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


async def graph_updates(graph: Any, state: AgentState) -> AsyncIterator[dict[str, Any]]:
    """Typed wrapper for consumers that need node-level update iteration."""
    async for update in graph.astream(state, stream_mode="updates"):
        yield update
