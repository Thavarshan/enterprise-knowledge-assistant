"""Build the model-backed LangGraph workflow with a deterministic mock path.

The supervisor and response nodes use an injected structured model provider.
Retrieval authorization remains server-side and citations are checked against
complete identities before answer chunks can reach the client.
"""

import asyncio
import re
from collections.abc import AsyncIterator
from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from langgraph.types import StreamWriter

from enterprise_assistant.agents.state import AgentState
from enterprise_assistant.domain.models import SearchResult, SourceCitation
from enterprise_assistant.llm.contracts import GroundedAnswer, ModelProvider
from enterprise_assistant.llm.providers import MockModelProvider
from enterprise_assistant.observability.events import ActivityEvent, EventType
from enterprise_assistant.retrieval.interfaces import Retriever
from enterprise_assistant.rlm.contracts import ExecutionBudget
from enterprise_assistant.rlm.executor import BoundedResearchExecutor
from enterprise_assistant.security.authorization import Role
from enterprise_assistant.tools.analysis import (
    AnalysisInputError,
    AnalysisResult,
    PythonAnalysisTool,
    parse_analysis_question,
)
from enterprise_assistant.tools.knowledge import KnowledgeSearchTool
from enterprise_assistant.tools.registry import (
    ToolAuthorizationError,
    ToolRegistry,
)

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


def _stream_event(
    writer: StreamWriter,
    state: AgentState,
    *,
    event_type: EventType,
    agent: str,
    node: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Send one validated execution event before a node update completes.

    Args:
        writer: LangGraph custom-stream writer injected into the node.
        state: Workflow state containing trusted correlation identifiers.
        event_type: Stable lifecycle category.
        agent: Logical agent or tool owner.
        node: Graph node currently executing.
        message: Concise status without prompts or provider details.
        metadata: Safe counts, identities, or stable error codes.
    """
    writer(
        _event(
            state,
            event_type=event_type,
            agent=agent,
            node=node,
            message=message,
            metadata=metadata,
        )
    )


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

    The StateGraph routes supervisor output to direct retrieval, recursive
    research, or validated arithmetic, then validates the final response.
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
    python_analysis = PythonAnalysisTool()

    async def supervisor(
        state: AgentState,
        writer: StreamWriter,
    ) -> dict[str, Any]:
        """Choose direct retrieval, bounded research, or arithmetic analysis.

        The provider returns a validated route only. Roles and retrieval
        policy remain trusted backend state and are not model outputs.

        Args:
            state: Shared graph state containing the question and IDs.
            writer: LangGraph custom event writer for live node status.

        Returns:
            A route field and an appended transition event.
        """
        _stream_event(
            writer,
            state,
            event_type="agent_start",
            agent="supervisor",
            node="supervisor",
            message="Supervisor started.",
        )
        try:
            decision = await language_model.classify_intent(
                state["question"], state.get("history", [])
            )
        except asyncio.CancelledError:
            _stream_event(
                writer,
                state,
                event_type="failure",
                agent="supervisor",
                node="supervisor",
                message="Supervisor execution was cancelled.",
                metadata={"error_code": "supervisor_cancelled"},
            )
            raise
        except Exception:
            _stream_event(
                writer,
                state,
                event_type="failure",
                agent="supervisor",
                node="supervisor",
                message="Supervisor could not choose a workflow.",
                metadata={"error_code": "supervisor_failed"},
            )
            raise
        route = decision.route
        _stream_event(
            writer,
            state,
            event_type="agent_complete",
            agent="supervisor",
            node="supervisor",
            message=f"Supervisor selected the {route} workflow.",
            metadata={"decision": route},
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

    async def research(
        state: AgentState,
        writer: StreamWriter,
    ) -> dict[str, Any]:
        """Execute a recursive, budgeted investigation with safe aggregation.

        Every leaf search passes through the same role-authorized tool
        registry as direct retrieval. The executor bounds recursion, search
        calls, result count, and elapsed time; partial failures leave
        completed sibling findings available to Response.

        Args:
            state: Authenticated graph state containing the question and IDs.
            writer: LangGraph custom event writer for node and search status.

        Returns:
            Aggregated evidence, execution counters, and activity events.

        Security:
            The model proposes query text only. Role and access filters are
            derived from the authenticated state by the search tool.
        """
        _stream_event(
            writer,
            state,
            event_type="agent_start",
            agent="research",
            node="research",
            message="Research started.",
        )
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

        def research_progress(
            event_type: str,
            metadata: dict[str, int | str],
        ) -> None:
            """Stream per-search lifecycle without query or content data.

            Args:
                event_type: Search start, completion, or failure category.
                metadata: Safe call counts or a stable failure code.
            """
            if event_type == "tool_start":
                message = "Started an authorized knowledge search."
                resolved_type: EventType = "tool_start"
            elif event_type == "tool_complete":
                message = "Authorized knowledge search completed."
                resolved_type = "tool_complete"
            else:
                message = "A research operation failed or hit its budget."
                resolved_type = "failure"
            _stream_event(
                writer,
                state,
                event_type=resolved_type,
                agent="research",
                node="research",
                message=message,
                metadata=dict(metadata),
            )

        budget = ExecutionBudget(
            max_depth=2,
            max_search_calls=4,
            max_documents=20,
            timeout_seconds=30,
        )
        try:
            report = await BoundedResearchExecutor(
                language_model,
                authorized_search,
                budget,
                on_progress=research_progress,
            ).execute(state["question"])
        except asyncio.CancelledError:
            _stream_event(
                writer,
                state,
                event_type="failure",
                agent="research",
                node="research",
                message="Research execution was cancelled.",
                metadata={"error_code": "research_cancelled"},
            )
            raise
        except Exception:
            _stream_event(
                writer,
                state,
                event_type="failure",
                agent="research",
                node="research",
                message="Research could not complete.",
                metadata={"error_code": "research_failed"},
            )
            raise
        _stream_event(
            writer,
            state,
            event_type="agent_complete",
            agent="research",
            node="research",
            message="Research completed.",
            metadata={
                "search_calls": report.search_calls,
                "finding_count": len(report.findings),
            },
        )
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

    async def retrieval(
        state: AgentState,
        writer: StreamWriter,
    ) -> dict[str, Any]:
        """Run the authorized knowledge-search tool for the user question.

        The role comes from graph state created by the API for the logged-in
        user. ToolRegistry checks policy before the handler derives access
        levels and calls the retriever.

        Args:
            state: Authenticated workflow state containing the question.
            writer: LangGraph custom event writer for node and tool status.

        Returns:
            Serialized results plus tool and retrieval events.

        Security:
            Do not construct this state from client-supplied role values.
        """
        _stream_event(
            writer,
            state,
            event_type="agent_start",
            agent="retrieval",
            node="retrieval",
            message="Retrieval started.",
        )
        role = Role(state["role"])
        query = state["question"]
        _stream_event(
            writer,
            state,
            event_type="tool_start",
            agent="retrieval",
            node="retrieval",
            message="Started an authorized knowledge search.",
            metadata={"tool": "knowledge_search"},
        )
        try:
            results = cast(
                list[SearchResult],
                await tool_registry.execute(
                    "knowledge_search",
                    role,
                    {"query": query, "role": role.value, "limit": 5},
                    {"knowledge_search": knowledge_search.run},
                ),
            )
        except asyncio.CancelledError:
            _stream_event(
                writer,
                state,
                event_type="failure",
                agent="retrieval",
                node="retrieval",
                message="Knowledge search was cancelled.",
                metadata={"error_code": "knowledge_search_cancelled"},
            )
            raise
        except Exception:
            _stream_event(
                writer,
                state,
                event_type="failure",
                agent="retrieval",
                node="retrieval",
                message="Knowledge search failed.",
                metadata={"error_code": "knowledge_search_failed"},
            )
            raise
        _stream_event(
            writer,
            state,
            event_type="tool_complete",
            agent="retrieval",
            node="retrieval",
            message="Authorized knowledge search completed.",
            metadata={
                "tool": "knowledge_search",
                "result_count": len(results),
            },
        )
        _stream_event(
            writer,
            state,
            event_type="agent_complete",
            agent="retrieval",
            node="retrieval",
            message="Retrieval completed.",
            metadata={"result_count": len(results)},
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
                event_type="retrieval",
                agent="retrieval",
                node="retrieval",
                message=f"Found {len(results)} accessible source chunk(s).",
                metadata={"sources": source_list},
            ),
        ]
        return {"results": serialized, "events": events}

    async def analysis(
        state: AgentState,
        writer: StreamWriter,
    ) -> dict[str, Any]:
        """Execute the strict arithmetic tool under server-side role policy.

        The user question must match the documented numeric grammar. The
        tool receives validated literals only and has no dynamic-code or
        external-data capabilities.

        Args:
            state: Authenticated graph state containing the user question.
            writer: LangGraph custom event writer for node and tool status.

        Returns:
            A structured result or stable safe error code with an event.
        """
        _stream_event(
            writer,
            state,
            event_type="agent_start",
            agent="analysis",
            node="analysis",
            message="Python analysis started.",
        )
        try:
            request = parse_analysis_question(state["question"])
        except AnalysisInputError:
            return _analysis_failure(
                state,
                code="analysis_input_invalid",
                message=(
                    "Use a supported calculation, such as calculate "
                    "average of 10, 20, 30."
                ),
            )

        role = Role(state["role"])
        try:
            tool_registry.authorize("python_analysis", role)
        except ToolAuthorizationError:
            return _analysis_failure(
                state,
                code="python_analysis_forbidden",
                message=(
                    "This account is not authorized to use Python analysis."
                ),
            )
        _stream_event(
            writer,
            state,
            event_type="tool_start",
            agent="analysis",
            node="analysis",
            message="Started the validated Python analysis tool.",
            metadata={"tool": "python_analysis"},
        )
        try:
            result = cast(
                AnalysisResult,
                await tool_registry.execute(
                    "python_analysis",
                    role,
                    request.model_dump(mode="python"),
                    {"python_analysis": python_analysis.run},
                ),
            )
        except asyncio.CancelledError:
            _stream_event(
                writer,
                state,
                event_type="failure",
                agent="analysis",
                node="analysis",
                message="Python analysis was cancelled.",
                metadata={"error_code": "python_analysis_cancelled"},
            )
            raise
        except ToolAuthorizationError:
            return _analysis_failure(
                state,
                code="python_analysis_forbidden",
                message=(
                    "This account is not authorized to use Python analysis."
                ),
            )
        except AnalysisInputError:
            return _analysis_failure(
                state,
                code="analysis_input_invalid",
                message="The requested calculation could not be completed.",
            )
        except Exception:
            _stream_event(
                writer,
                state,
                event_type="failure",
                agent="analysis",
                node="analysis",
                message="Python analysis failed.",
                metadata={"error_code": "python_analysis_failed"},
            )
            raise

        _stream_event(
            writer,
            state,
            event_type="tool_complete",
            agent="analysis",
            node="analysis",
            message="Python analysis completed.",
            metadata={
                "tool": "python_analysis",
                "operation": result.operation,
                "input_count": result.input_count,
            },
        )
        _stream_event(
            writer,
            state,
            event_type="agent_complete",
            agent="analysis",
            node="analysis",
            message="Python analysis completed.",
        )

        return {
            "analysis_result": result.model_dump(mode="json"),
            "events": [],
        }

    def _analysis_failure(
        state: AgentState,
        *,
        code: str,
        message: str,
    ) -> dict[str, Any]:
        """Create a safe failed-analysis state update.

        Args:
            state: Authenticated graph state used for event correlation.
            code: Stable error identifier, never provider text.
            message: Static caller-facing description.

        Returns:
            Analysis failure code and one structured activity event.
        """
        return {
            "analysis_error": code,
            "events": [
                _event(
                    state,
                    event_type="failure",
                    agent="analysis",
                    node="analysis",
                    message=message,
                    metadata={"error_code": code},
                )
            ],
        }

    async def response(
        state: AgentState,
        writer: StreamWriter,
    ) -> dict[str, Any]:
        """Respond from authorized evidence or a validated analysis result.

        Numeric analysis results use a fixed response. Retrieved evidence is
        passed to the model, and empty search results produce a fixed message.

        Args:
            state: Workflow state containing serialized search results.
            writer: LangGraph custom event writer for node and failure status.

        Returns:
            Response text, citation records, and a transition event.
        """
        _stream_event(
            writer,
            state,
            event_type="agent_start",
            agent="response",
            node="response",
            message="Response started.",
        )
        results = [
            SearchResult.model_validate(result)
            for result in state.get("results", [])
        ]
        analysis_data = state.get("analysis_result")
        analysis_error = state.get("analysis_error")
        citations: list[SourceCitation]
        if analysis_data:
            result = AnalysisResult.model_validate(analysis_data)
            label = result.operation.title()
            answer = (
                f"{label} of {result.field} over {result.input_count} "
                f"value(s): {result.value:g}."
            )
            citations = []
            grounded = True
        elif analysis_error == "python_analysis_forbidden":
            answer = "This account is not authorized to use Python analysis."
            citations = []
            grounded = True
        elif analysis_error == "analysis_input_invalid":
            answer = (
                "Use a supported calculation, such as "
                "calculate average of 10, 20, 30."
            )
            citations = []
            grounded = True
        elif results:
            try:
                model_answer = await language_model.generate_answer(
                    state["question"],
                    results,
                    state.get("history", []),
                )
            except asyncio.CancelledError:
                _stream_event(
                    writer,
                    state,
                    event_type="failure",
                    agent="response",
                    node="response",
                    message="Response generation was cancelled.",
                    metadata={"error_code": "response_cancelled"},
                )
                raise
            except Exception:
                _stream_event(
                    writer,
                    state,
                    event_type="failure",
                    agent="response",
                    node="response",
                    message="Grounded response generation failed.",
                    metadata={"error_code": "response_generation_failed"},
                )
                raise
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
        if analysis_data:
            response_message = "Returned a validated Python analysis result."
        elif analysis_error:
            response_message = "Returned a safe Python analysis rejection."
        else:
            response_message = "Generated a response from authorized evidence."
        _stream_event(
            writer,
            state,
            event_type="agent_complete",
            agent="response",
            node="response",
            message="Response completed.",
            metadata={"citation_count": len(citations)},
        )
        events = [
            _event(
                state,
                event_type="agent_transition",
                agent="response",
                node="response",
                message=response_message,
                metadata={"citation_count": len(citations)},
            )
        ]
        return {
            "response": answer,
            "citations": [citation.model_dump() for citation in citations],
            "answer_grounded": grounded,
            "events": events,
        }

    async def validate(
        state: AgentState,
        writer: StreamWriter,
    ) -> dict[str, Any]:
        """Withhold answers whose citation markers do not validate.

        The node checks markers against citations and retrieved chunk IDs.
        It emits response chunks only after validation; failure replaces the
        answer and emits a generic failure event.

        Args:
            state: Workflow state containing answer, citations, and results.
            writer: LangGraph custom event writer for validation lifecycle.

        Returns:
            Final response state and validation/activity events.

        Security:
            Only validated content is emitted as response chunks.
        """
        _stream_event(
            writer,
            state,
            event_type="agent_start",
            agent="response",
            node="validate",
            message="Citation validation started.",
        )
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
        _stream_event(
            writer,
            state,
            event_type="agent_complete",
            agent="response",
            node="validate",
            message=(
                "Citation validation completed."
                if valid
                else "Citation validation rejected the response."
            ),
            metadata={"validation_passed": valid},
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
        {
            "retrieval": "retrieval",
            "research": "research",
            "analysis": "analysis",
        },
    )
    graph.add_node("analysis", analysis)
    graph.add_edge("research", "response")
    graph.add_edge("retrieval", "response")
    graph.add_edge("analysis", "response")
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
