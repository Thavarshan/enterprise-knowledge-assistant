"""Provide unauthenticated liveness and readiness endpoints.

Liveness only confirms that the API process can answer. Readiness checks the
configured session store and returns HTTP 503 when that dependency is
unhealthy.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Report process liveness without checking downstream services.

    Returns:
        A small status payload when the event loop can serve the request.
    """
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> dict[str, str]:
    """Report whether the configured session store is reachable.

    The current readiness probe checks SQLite only; it does not verify
    Pinecone or LangSmith.

    Args:
        request: Request containing the configured session store.

    Returns:
        Ready status when the store health check succeeds.

    Raises:
        HTTPException: 503 when the session store is unavailable.
    """
    container: Any = request.app.state.container
    if not container.memory.healthcheck():
        raise HTTPException(
            status_code=503, detail="Session store is not ready.")
    return {"status": "ready"}
