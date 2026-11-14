"""Build the model-backed LangGraph workflow with a deterministic mock path.

The supervisor and response nodes use an injected structured model provider.
Retrieval authorization remains server-side and citations are checked against
complete identities before answer chunks can reach the client.
"""

import re
from collections.abc import AsyncIterator
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from enterprise_assistant.agents.state import AgentState
from enterprise_assistant.domain.models import SearchResult, SourceCitation
from enterprise_assistant.llm.contracts import GroundedAnswer, ModelProvider
from enterprise_assistant.llm.providers import MockModelProvider
from enterprise_assistant.observability.events import ActivityEvent, EventType
from enterprise_assistant.retrieval.interfaces import Retriever
from enterprise_assistant.rlm.contracts import ExecutionBudget
from enterprise_assistant.rlm.executor import BoundedResearchExecutor
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
    retrieved_identities: frozenset[tuple[str, str]],
) -> bool:
    """Verify markers against complete retrieved source identities.

    The marker set must equal citations whose document and chunk IDs both
    occurred in this turn. An answer without markers is valid only when it
    has no citations.

    Args:
        response: Rendered answer containing bracketed source markers.
        citations: Citation objects produced from search results.
        retrieved_identities: Document/chunk pairs returned this turn.

    Returns:
        True when marker and citation sets satisfy the current policy.

    """
    markers = set(_CITATION_PATTERN.findall(response))
    allowed_markers = {
        f"{citation.document_id}#{citation.chunk_id}"
        for citation in citations
        if (citation.document_id, citation.chunk_id) in retrieved_identities
    }
    if not markers:
        return not citations
    return (
        markers == allowed_markers
        and len(allowed_markers) == len(citations)
    )


def render_grounded_answer(
    answer: GroundedAnswer,
    results: list[SearchResult],
) -> tuple[str, list[SourceCitation], bool]:
    """Render claims and canonical citations from authorized search results.

    Every model source identity is matched to a full document/chunk pair.
    An unknown identity marks the response ungrounded so validation withholds
    it instead of trusting source fields returned by the model.

    Args:
        answer: Structured model claims and source identities.
        results: Evidence already filtered by server-side authorization.

    Returns:
        Rendered answer, canonical citations, and grounding status.
    """
    evidence = {
        (
            result.chunk.metadata.document_id,
            result.chunk.metadata.chunk_id,
        ): result.chunk
        for result in results
    }
    citations: dict[tuple[str, str], SourceCitation] = {}
    rendered_claims: list[str] = []
    grounded = True
    for claim in answer.claims:
        markers: list[str] = []
        for identity in claim.citations:
            key = (identity.document_id, identity.chunk_id)
            chunk = evidence.get(key)
            if chunk is None:
                grounded = False
                continue
            citations[key] = SourceCitation.from_chunk(chunk)
            markers.append(f"[{key[0]}#{key[1]}]")
        if markers:
            rendered_claims.append(f"{claim.text} {' '.join(markers)}")
        else:
            rendered_claims.append(claim.text)
    return "\n\n".join(rendered_claims), list(citations.values()), grounded


def build_graph(
    retriever: Retriever,
    tool_registry: ToolRegistry,
    model_provider: ModelProvider | None = None,
) -> Any:
    """Compile the bounded conversation workflow from injected adapters.

    The StateGraph routes supervisor output to direct retrieval or a
    recursive research executor, then runs response and citation validation.
    Node events append through the reducer declared on AgentState.

    Args:
        retriever: Search adapter used by the knowledge tool.
        tool_registry: Backend policy registry for tool dispatch.
        model_provider: Structured provider; defaults to deterministic mock.

    Returns:
        A compiled LangGraph runnable consumed by ChatService.

    Notes:
        Conversation history is supplied by the owner-scoped service. The
        graph itself does not use a checkpointer.
    """
    language_model = model_provider or MockModelProvider()
    knowledge_search = KnowledgeSearchTool(retriever)

    async def supervisor(state: AgentState) -> dict[str, Any]:
        """Choose the direct-retrieval or bounded-research route.

        The provider returns a validated route only. Roles and retrieval
        policy remain trusted backend state and are not model outputs.

        Args:
            state: Shared graph state containing the question and IDs.

        Returns:
            A route field and an appended transition event.
        """
        decision = await language_model.classify_intent(
            state["question"], state.get("history", [])
        )
        route = decision.route
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
        """Execute a recursive, budgeted investigation with safe aggregation.

        Every leaf search passes through the same role-authorized tool
        registry as direct retrieval. The executor bounds recursion, search
        calls, result count, and elapsed time; partial failures leave
        completed sibling findings available to Response.

        Args:
            state: Authenticated graph state containing the question and IDs.

        Returns:
            Aggregated evidence, execution counters, and activity events.

        Security:
            The model proposes query text only. Role and access filters are
            derived from the authenticated state by the search tool.
        """
        role = Role(state["role"])

        async def authorized_search(
            query: str,
            limit: int,
        ) -> list[SearchResult]:
            """Run a leaf search after checking backend tool policy.

            Args:
                query: Validated task text from the decomposition contract.
                limit: Remaining document budget for this search.

            Returns:
                Authorized ranked evidence for the task.
            """
            return cast(
                list[SearchResult],
                await tool_registry.execute(
                    "knowledge_search",
                    role,
                    {"query": query, "role": role.value, "limit": limit},
                    {"knowledge_search": knowledge_search.run},
                ),
            )

        budget = ExecutionBudget(
            max_depth=2,
            max_search_calls=4,
            max_documents=20,
            timeout_seconds=30,
        )
        report = await BoundedResearchExecutor(
            language_model,
            authorized_search,
            budget,
        ).execute(state["question"])
        results = list(report.results)
        sources = [
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
                event_type="agent_transition",
                agent="research",
                node="research",
                message="Completed bounded recursive investigation.",
                metadata={
                    "search_calls": report.search_calls,
                    "decomposition_calls": report.decomposition_calls,
                    "max_depth_reached": report.max_depth_reached,
                },
            ),
            _event(
                state,
                event_type="tool_execution",
                agent="research",
                node="research",
                message=(
                    f"Executed {report.search_calls} authorized "
                    "sub-investigation search(es)."
                ),
                metadata={
                    "tool": "knowledge_search",
                    "search_calls": report.search_calls,
                    "failure_count": len(report.failure_codes),
                },
            ),
            _event(
                state,
                event_type="retrieval",
                agent="research",
                node="research",
                message=(
                    f"Aggregated {len(results)} source chunk(s) "
                    "from the investigation."
                ),
                metadata={"sources": sources},
            ),
        ]
        if report.failure_codes:
            events.append(
                _event(
                    state,
                    event_type="failure",
                    agent="research",
                    node="research",
                    message=(
                        "Some investigation branches were incomplete; "
                        "available findings were retained."
                    ),
                    metadata={
                        "error_code": "research_partial_failure",
                        "failure_count": len(report.failure_codes),
                    },
                )
            )
        return {
            "results": [result.model_dump(mode="json") for result in results],
            "investigation_findings": [
                {
                    "task": finding.task,
                    "sources": [
                        {
                            "document_id": result.chunk.metadata.document_id,
                            "chunk_id": result.chunk.metadata.chunk_id,
                        }
                        for result in finding.results
                    ],
                }
                for finding in report.findings
            ],
            "investigation_summary": {
                "search_calls": report.search_calls,
                "decomposition_calls": report.decomposition_calls,
                "max_depth_reached": report.max_depth_reached,
                "failure_codes": list(report.failure_codes),
            },
            "events": events,
        }

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
        query = state["question"]
        results = await tool_registry.execute(
            "knowledge_search",
            role,
            {"query": query, "role": role.value,
                "limit": 5},
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
        """Generate grounded claims from authorized retrieved chunks.

        Empty results produce a fixed no-evidence response without a model
        call. Model citations are canonicalized from the retrieved chunks.

        Args:
            state: Workflow state containing serialized search results.

        Returns:
            Response text, citation records, and a transition event.
        """
        results = [
            SearchResult.model_validate(result)
            for result in state.get("results", [])
        ]
        if results:
            model_answer = await language_model.generate_answer(
                state["question"],
                results,
                state.get("history", []),
            )
            answer, citations, grounded = render_grounded_answer(
                model_answer,
                results,
            )
        else:
            answer = (
                "I could not find an accessible document "
                "that answers this question."
            )
            citations = []
            grounded = True
        events = [
            _event(
                state,
                event_type="agent_transition",
                agent="response",
                node="response",
                message=(
                    "Generated a response from authorized evidence."
                ),
                metadata={"citation_count": len(citations)},
            )
        ]
        return {
            "response": answer,
            "citations": [citation.model_dump() for citation in citations],
            "answer_grounded": grounded,
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
        retrieved_identities = frozenset(
            (
                parsed.chunk.metadata.document_id,
                parsed.chunk.metadata.chunk_id,
            )
            for result in state.get("results", [])
            for parsed in [SearchResult.model_validate(result)]
        )
        valid = (
            state.get("answer_grounded", True)
            and validate_citations(
                state.get("response", ""),
                citations,
                retrieved_identities,
            )
        )
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
    graph.add_edge("research", "response")
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
