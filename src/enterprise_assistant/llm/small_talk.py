"""Provide brief, deterministic replies for conversational greetings.

Small talk is limited to common pleasantries and capability questions. The
helper does not answer factual questions or inspect conversation history.
"""

import re

_GREETING = frozenset(
    {
        "hello",
        "hello there",
        "hi",
        "hi there",
        "hey",
        "hey there",
        "howdy",
        "good morning",
        "good afternoon",
        "good evening",
        "how are you",
        "how are you doing",
        "how is it going",
        "hows it going",
        "hello how are you",
        "hi how are you",
        "hey how are you",
        "whats up",
        "nice to meet you",
    }
)
_THANKS = frozenset(
    {
        "thanks",
        "thank you",
        "thanks for your help",
        "thank you for your help",
        "much appreciated",
    }
)
_FAREWELL = frozenset(
    {
        "bye",
        "goodbye",
        "good night",
        "see you",
        "see you later",
    }
)
_CAPABILITIES = frozenset(
    {
        "what can you do",
        "what can you help me with",
        "who are you",
        "what do you do",
        "what is your purpose",
        "whats your purpose",
        "can you help me",
    }
)


def small_talk_response(question: str) -> str | None:
    """Return a short product-aware reply for a plain pleasantry.

    Args:
        question: User text selected for deterministic phrase matching.

    Returns:
        A conversational response, or ``None`` for requests that need a
        workflow such as retrieval, research, or analysis.
    """
    normalized = re.sub(r"[^a-z0-9\s]", "", question.casefold())
    normalized = " ".join(normalized.split())

    if normalized in _GREETING:
        return (
            "Hello! I can search accessible runbooks, policies, and incident "
            "reports and investigate multi-part questions. If your role "
            "allows it, I can also help with supported calculations. What "
            "would you like to explore?"
        )
    if normalized in _THANKS:
        return (
            "You’re welcome! I can search accessible knowledge or help with "
            "another question whenever you’re ready."
        )
    if normalized in _FAREWELL:
        return (
            "Goodbye! Come back whenever you need help with company "
            "knowledge."
        )
    if normalized in _CAPABILITIES:
        return (
            "I can search accessible runbooks, policies, and incident "
            "reports and investigate multi-part questions. If your role "
            "allows it, I can also help with supported calculations. What "
            "would you like to try?"
        )
    return None
