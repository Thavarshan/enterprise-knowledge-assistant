"""Define validated model inputs, outputs, and provider boundaries.

Structured model output is parsed before it enters graph state. Citation
identities retain both document and chunk IDs so response validation can
compare complete evidence identities.
"""

from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from enterprise_assistant.domain.models import SearchResult
from enterprise_assistant.memory.models import ChatMessage
from enterprise_assistant.rlm.contracts import TaskDecomposition

Workflow = Literal["small_talk", "retrieval", "research", "analysis"]


class SupervisorDecision(BaseModel):
    """Validate the supervisor's allowed workflow selection.

    The model output contains routing only. It cannot supply roles, access
    labels, departments, tool permissions, or retrieval filters. Analysis
    inputs are independently parsed and validated by the Python tool.

    Attributes:
        route: Small talk, retrieval, research, or explicit arithmetic.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    route: Workflow


class CitationIdentity(BaseModel):
    """Identify one source using its complete document and chunk IDs.

    Attributes:
        document_id: Stable ID of the parent source document.
        chunk_id: Stable ID of the cited passage.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(min_length=1, max_length=128)
    chunk_id: str = Field(min_length=1, max_length=128)


class GroundedClaim(BaseModel):
    """Represent one answer claim tied to one or more source chunks.

    Attributes:
        text: User-facing claim generated from authorized evidence.
        citations: Complete source identities supporting the claim.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=1200)
    citations: list[CitationIdentity] = Field(min_length=1, max_length=5)


class GroundedAnswer(BaseModel):
    """Validate a response as bounded, individually cited claims.

    Attributes:
        claims: Statements that must each cite returned evidence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    claims: list[GroundedClaim] = Field(min_length=1, max_length=12)


class ModelProvider(Protocol):
    """Define the asynchronous model tasks used by graph agents.

    Provider results are structured and validated before graph nodes use
    them. Implementations must preserve cancellation and enforce request
    timeouts. They never receive or decide authorization policy.
    """

    async def classify_intent(
        self,
        question: str,
        history: Sequence[ChatMessage] = (),
    ) -> SupervisorDecision:
        """Choose a conversational, retrieval, research, or analysis route.

        Args:
            question: Current untrusted user request.
            history: Owner-scoped prior messages from the same session.

        Returns:
            Validated workflow decision with no permission fields.
        """
        ...

    async def generate_answer(
        self,
        question: str,
        evidence: Sequence[SearchResult],
        history: Sequence[ChatMessage] = (),
    ) -> GroundedAnswer:
        """Generate claims tied to the supplied authorized evidence.

        Args:
            question: Current user request.
            evidence: Results already filtered by backend authorization.
            history: Owner-scoped prior messages from the same session.

        Returns:
            Structured claims with complete citation identities.
        """
        ...

    async def decompose_question(
        self, question: str
    ) -> TaskDecomposition:
        """Split a complex investigation into bounded independent tasks.

        Args:
            question: User request selected for research.

        Returns:
            Validated objective and one to four retrieval subtasks.
        """
        ...

    async def aclose(self) -> None:
        """Release provider resources during application shutdown.

        Providers without external resources implement this as a no-op.
        """
        ...
