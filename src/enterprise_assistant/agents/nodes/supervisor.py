"""Choose a deterministic route for each user question.

Questions containing one of the explicit investigation terms use the bounded
Research path. All other questions go directly to retrieval. This policy is
keyword-based and is not an LLM supervisor.
"""

from typing import Literal

Workflow = Literal["retrieval", "research"]


def select_workflow(question: str) -> Workflow:
    """Route explicit investigation requests to the Research node.

    Case-insensitive checks for three fixed terms select Research; every
    other question goes directly to retrieval. This is not an LLM
    supervisor.

    Args:
        question: Validated natural-language request.

    Returns:
        The retrieval or research workflow label.
    """
    normalized = question.casefold()
    investigation_words = ("investigate", "compare", "analyze")
    if any(word in normalized for word in investigation_words):
        return "research"
    return "retrieval"
