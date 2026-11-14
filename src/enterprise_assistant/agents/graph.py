"""Build and run the deterministic LangGraph conversation workflow.

The graph routes each question to direct retrieval or one bounded Research
planning step, then retrieves role-filtered evidence, creates a deterministic
answer, and validates its citation markers before emitting response chunks.

Node updates use a reducer-backed event list for explainability. There is no
model call, tool loop, retry policy, or checkpointer in this implementation;
the graph terminates after the validation node.
"""

import re
from collections.abc import AsyncIterator
from typing import Any

from langgraph.graph import END, START, StateGraph

from enterprise_assistant.agents.nodes.research import plan_research
from enterprise_assistant.agents.nodes.response import grounded_response
from enterprise_assistant.agents.nodes.retrieval import selected_query
from enterprise_assistant.agents.nodes.supervisor import select_workflow
from enterprise_assistant.agents.state import AgentState
from enterprise_assistant.domain.models import SearchResult, SourceCitation
from enterprise_assistant.observability.events import ActivityEvent, EventType
from enterprise_assistant.retrieval.interfaces import Retriever
from enterprise_assistant.rlm.contracts import ExecutionBudget
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
    """Serialize one graph activity event for downstream consumers.

    The helper attaches request and session correlation from trusted
    graph state and returns JSON-compatible event data for the reducer.

    Args:
        state: Workflow state with request and session IDs.
        event_type: Stable event category presented to the UI.
        agent: Logical agent name associated with this transition.
        node: Graph node that produced the event.
        message: Concise status text without hidden reasoning.
        metadata: Optional structured evidence or status fields.

    Returns:
        A dictionary validated by the ActivityEvent schema.

    Security:
        Metadata must not contain secrets or chain-of-thought.
    """
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
    """Verify response markers against citations and retrieved chunk IDs.

    The marker set must equal citations whose chunk IDs occurred in this
    turn. An answer without markers is valid only when it has no
    citations.

    Args:
        response: Rendered answer containing bracketed source markers.
        citations: Citation objects produced from search results.
        retrieved_chunk_ids: Chunk IDs returned for this retrieval turn.

    Returns:
        True when marker and citation sets satisfy the current policy.

    Notes:
        The check compares chunk IDs, not document/chunk pairs. The
        graph builds citations from results; compare full pairs before
        accepting untrusted citation objects.
    """
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
    """Compile the bounded conversation workflow from injected adapters.

    The StateGraph routes supervisor output to retrieval or one Research
    step, then runs response and citation validation before ending. Node
    events append through the reducer declared on AgentState.

    Args:
        retriever: Search adapter used by the knowledge tool.
        tool_registry: Backend policy registry for tool dispatch.

    Returns:
        A compiled LangGraph runnable consumed by ChatService.

    Notes:
        No checkpointer is supplied, so thread IDs do not persist state.
        The graph has no cycles or model-driven route selection.
    """

    async def supervisor(state: AgentState) -> dict[str, Any]:
        """Choose the direct-retrieval or bounded-research route.

        A deterministic keyword policy evaluates the question. The node
        returns its route and an activity event without asking a model to
        decide.

        Args:
            state: Shared graph state containing the question and IDs.

        Returns:
            A route field and an appended transition event.
        """
        route = select_workflow(state["question"])
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
        """Create a bounded structured plan for investigation questions.

        The current planner retains one query and a one-level budget. Its
        plan is passed to retrieval; no recursive calls or generated code
        run.

        Args:
            state: Shared graph state containing the question and IDs.

        Returns:
            A serialized plan and an appended transition event.
        """
        plan, queries, budget = plan_research(state["question"])
        event = _event(
            state,
            event_type="agent_transition",
            agent="research",
            node="research",
            message="Prepared a bounded structured search plan.",
            metadata={"query_count": len(
                queries), "max_depth": budget.max_depth},
        )
        return {
            "search_plan": {
                "queries": list(queries),
                "max_depth": plan.max_depth,
            },
            "events": [event],
        }

    knowledge_search = KnowledgeSearchTool(retriever)

    async def retrieval(state: AgentState) -> dict[str, Any]:
        """Run the authorized knowledge-search tool for the selected query.

        The role comes from graph state created by the API for the logged-in
        user. ToolRegistry checks policy before the handler derives access
        levels and calls the retriever.

        Args:
            state: Authenticated workflow state and optional search plan.

        Returns:
            Serialized results plus tool and retrieval events.

        Security:
            Do not construct this state from client-supplied role values.
        """
        role = Role(state["role"])
        query = selected_query(state["question"], state.get("search_plan"))
        results = await tool_registry.execute(
            "knowledge_search",
            role,
            {"query": query, "role": role.value,
                "limit": ExecutionBudget().max_documents},
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
                metadata={"tool": "knowledge_search",
                          "result_count": len(results)},
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
        """Build a deterministic answer from ranked retrieved chunks.

        The node validates serialized results, selects at most two chunks,
        and derives citations from their metadata. Empty results produce a
        fixed no-evidence response.

        Args:
            state: Workflow state containing serialized search results.

        Returns:
            Response text, citation records, and a transition event.
        """
        results = [SearchResult.model_validate(
            result) for result in state.get("results", [])]
        answer, citations = grounded_response(results)
        events = [
            _event(
                state,
                event_type="agent_transition",
                agent="response",
                node="response",
                message=(
                    "Prepared a response grounded in "
                    "retrieved fixture evidence."
                ),
                metadata={"citation_count": len(citations)},
            )
        ]
        return {
            "response": answer,
            "citations": [citation.model_dump() for citation in citations],
            "events": events,
        }

    async def validate(state: AgentState) -> dict[str, Any]:
        """Withhold answers whose citation markers do not validate.

        The node checks markers against citations and retrieved chunk IDs.
        It emits response chunks only after validation; failure replaces the
        answer and emits a generic failure event.

        Args:
            state: Workflow state containing answer, citations, and results.

        Returns:
            Final response state and validation/activity events.

        Security:
            Only validated content is emitted as response chunks.
        """
        citations = [
            SourceCitation.model_validate(citation)
            for citation in state.get("citations", [])
        ]
        retrieved_ids = frozenset(
            SearchResult.model_validate(result).chunk.metadata.chunk_id
            for result in state.get("results", [])
        )
        valid = validate_citations(
            state.get("response", ""), citations, retrieved_ids)
        answer = state.get("response", "")
        if not valid:
            answer = (
                "I could not return a response because its source citations "
                "did not validate."
            )
            citations = []
        event = _event(
            state,
            event_type="validation",
            agent="response",
            node="validate",
            message=(
                "Citation references validated."
                if valid
                else "Citation validation failed."
            ),
            metadata={"valid": valid, "citation_count": len(citations)},
        )
        events = [event]
        if valid:
            # The UI receives response text only after citation validation;
            # chunks are activity payloads, not tokens from a model stream.
            events.extend(
                _event(
                    state,
                    event_type="response_chunk",
                    agent="response",
                    node="validate",
                    message=answer[start: start + 80],
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
                    message=(
                        "The response was withheld because its citations "
                        "did not validate."
                    ),
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
    # The topology is acyclic: each turn reaches validation and END once.
    graph.add_edge("validate", END)
    return graph.compile()


async def graph_updates(
    graph: Any, state: AgentState
) -> AsyncIterator[dict[str, Any]]:
    """Yield LangGraph node updates from a compiled workflow.

    This wrapper preserves the framework update stream for consumers
    that need raw node-to-update mappings rather than ActivityEvent
    objects.

    Args:
        graph: Compiled graph exposing the asynchronous stream API.
        state: Initial shared graph state for this execution.

    Yields:
        One node update mapping for each graph step.
    """
    async for update in graph.astream(state, stream_mode="updates"):
        yield update
