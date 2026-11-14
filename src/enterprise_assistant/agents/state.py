"""Define the shared TypedDict state for the LangGraph workflow.

Node updates share identity, question, route, plan, result, response, and
citation fields. The `events` field uses `operator.add` so updates append
activity records instead of replacing records from earlier nodes.
"""

import operator
from typing import Annotated, Any, Literal

from typing_extensions import TypedDict

from enterprise_assistant.memory.models import ChatMessage


class AgentState(TypedDict, total=False):
    """Represent values shared between LangGraph nodes.

    Keys are optional at the type level because each node returns a
    partial update. The API creates identity and question fields; nodes
    add routing, evidence, response, and validation data.

    Attributes:
        request_id: Correlation ID propagated from the API.
        session_id: Owner-scoped conversation identifier.
        user_id: Server-resolved user ID for the turn.
        role: Server-resolved role used by tool policy.
        question: Validated user question for the current turn.
        history: Owner-scoped messages available as model context.
        route: Supervisor choice: retrieval or research.
        investigation_findings: Subtasks paired with returned source IDs.
        investigation_summary: Bounded search and decomposition counters.
        results: Serialized ranked evidence chunks.
        response: Answer text after response construction.
        citations: Citation metadata copied from retrieved chunks.
        validation_passed: Result of the citation gate.
        answer_grounded: Whether model citations map to retrieved evidence.
        events: Event dictionaries appended with operator.add.

    Security:
        Identity and role values must come from API authentication, not
        request fields.
    """
    request_id: str
    session_id: str
    user_id: str
    role: str
    question: str
    history: list[ChatMessage]
    route: Literal["retrieval", "research"]
    investigation_findings: list[dict[str, Any]]
    investigation_summary: dict[str, Any]
    results: list[dict[str, Any]]
    response: str
    citations: list[dict[str, str]]
    validation_passed: bool
    answer_grounded: bool
    # The list reducer appends node updates instead of replacing prior events.
    events: Annotated[list[dict[str, Any]], operator.add]
