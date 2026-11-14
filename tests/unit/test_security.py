"""Role enforcement and token bucket behavior."""

import pytest

from enterprise_assistant.security.authorization import Role
from enterprise_assistant.security.rate_limiting import (
    RateLimitExceeded,
    TokenBucketRateLimiter,
)
from enterprise_assistant.tools.registry import (
    ToolAuthorizationError,
    ToolRegistry,
)


def test_tool_registry_rejects_viewer_before_handler_runs() -> None:
    registry = ToolRegistry()
    assert registry.authorize(
        "knowledge_search", Role.VIEWER).name == "knowledge_search"
    with pytest.raises(ToolAuthorizationError):
        registry.authorize("python_analysis", Role.VIEWER)
    assert registry.authorize("mcp", Role.ANALYST).name == "mcp"
    assert registry.authorize(
        "python_analysis", Role.ADMINISTRATOR).name == "python_analysis"


def test_token_bucket_refills_per_user() -> None:
    now = [0.0]
    limiter = TokenBucketRateLimiter(2, 1, clock=lambda: now[0])
    limiter.consume("viewer")
    limiter.consume("viewer")
    with pytest.raises(RateLimitExceeded) as error:
        limiter.consume("viewer")
    assert error.value.retry_after_seconds == pytest.approx(1)

    limiter.consume("analyst")
    now[0] = 1.0
    limiter.consume("viewer")
