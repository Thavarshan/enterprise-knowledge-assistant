"""Verify an actual OpenAI response when live credentials are configured.

The test is opt-in through OPENAI_API_KEY. It uses synthetic evidence only
and validates both structured supervisor output and cited response output.
"""

import pytest

from enterprise_assistant.config.settings import get_settings
from enterprise_assistant.domain.models import (
    DocumentChunk,
    DocumentMetadata,
    SearchResult,
)
from enterprise_assistant.llm.providers import OpenAIModelProvider


@pytest.mark.integration
@pytest.mark.asyncio
async def test_openai_provider_returns_structured_live_responses() -> None:
    """Verify the configured model responds to route and answer requests.

    The small synthetic passage prevents customer information from entering
    the external provider during this integration check.
    """
    settings = get_settings()
    if not settings.openai_api_key:
        pytest.skip("OPENAI_API_KEY is not configured.")

    provider = OpenAIModelProvider(
        settings.openai_api_key,
        settings.openai_model,
        settings.llm_timeout_seconds,
    )
    chunk = DocumentChunk(
        content=(
            "Incident INC-DEMO-01: a payment gateway retry timeout created "
            "duplicate authorizations. The mitigation disabled retries."
        ),
        metadata=DocumentMetadata(
            document_id="incident-demo-01",
            chunk_id="incident-demo-01-001",
            title="Synthetic payment incident",
            department="payments",
            document_type="incident",
            access_level="viewer",
            created_date="2026-01-01",
            source="sample://incidents/incident-demo-01",
        ),
    )
    result = SearchResult(chunk=chunk, score=1.0, rank=1)
    try:
        decision = await provider.classify_intent(
            "What happened in the payment incident?"
        )
        greeting_decision = await provider.classify_intent("Hello!")
        answer = await provider.generate_answer(
            "What caused the duplicate authorizations?",
            [result],
        )
    finally:
        await provider.aclose()

    assert decision.route == "retrieval"
    assert greeting_decision.route == "small_talk"
    assert answer.claims
    allowed = {
        (chunk.metadata.document_id, chunk.metadata.chunk_id),
    }
    assert all(
        (item.document_id, item.chunk_id) in allowed
        for claim in answer.claims
        for item in claim.citations
    )
