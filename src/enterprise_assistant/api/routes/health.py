"""Unauthenticated liveness and readiness checks."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> dict[str, str]:
    container: Any = request.app.state.container
    if not container.memory.healthcheck():
        raise HTTPException(
            status_code=503, detail="Session store is not ready.")
    return {"status": "ready"}
