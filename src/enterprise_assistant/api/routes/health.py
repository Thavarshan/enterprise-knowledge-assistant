"""Provide unauthenticated liveness and readiness endpoints.

Liveness only confirms that the API process can answer. Readiness checks the
configured session store and returns HTTP 503 when that dependency is
unhealthy.
"""

import os
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["health"])
_RELEASE_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


@router.get("/health")
async def health() -> dict[str, str]:
    """Report process liveness without checking downstream services.

    Returns:
        A small status payload when the event loop can serve the request.
    """
    return {"status": "ok"}


@router.get("/version")
async def version(request: Request) -> dict[str, str]:
    """Expose the immutable source revision serving this API process.

    Returns:
        The validated source SHA and whether deterministic mock mode is
        active. Local runs without release metadata report ``unknown``.
    """
    release_sha = os.environ.get("APP_RELEASE_SHA", "").lower()
    if not _RELEASE_SHA_PATTERN.fullmatch(release_sha):
        release_sha = os.environ.get("VERCEL_GIT_COMMIT_SHA", "").lower()
    if not _RELEASE_SHA_PATTERN.fullmatch(release_sha):
        release_sha = "unknown"
    settings: Any = request.app.state.container.settings
    return {
        "release_sha": release_sha,
        "mode": "mock" if settings.mock_mode else "live",
    }


@router.get("/ready")
async def ready(request: Request) -> dict[str, str]:
    """Report whether the configured session store is reachable.

    The readiness probe checks only the configured session store. It does
    not verify Pinecone or LangSmith.

    Args:
        request: Request containing the configured session store.

    Returns:
        Ready status when the store health check succeeds.

    Raises:
        HTTPException: 503 when the session store is unavailable.
    """
    container: Any = request.app.state.container
    healthy = await container.memory.healthcheck()
    if not healthy:
        raise HTTPException(
            status_code=503, detail="Session store is not ready.")
    return {"status": "ready"}
