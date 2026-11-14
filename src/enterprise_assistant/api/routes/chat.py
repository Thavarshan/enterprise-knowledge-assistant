"""Owned session endpoints and graph-backed SSE conversation endpoint."""

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from enterprise_assistant.api.dependencies.auth import get_current_user
from enterprise_assistant.api.schemas.chat import (
    ChatStreamRequest,
    CreateSessionRequest,
    MessageResponse,
    SessionDetailResponse,
    SessionResponse,
)
from enterprise_assistant.memory.models import ChatSession
from enterprise_assistant.observability.events import ActivityEvent, encode_sse
from enterprise_assistant.security.authentication import AuthenticatedUser
from enterprise_assistant.security.rate_limiting import RateLimitExceeded

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    payload: CreateSessionRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
) -> SessionResponse:
    session = request.app.state.container.memory.create_session(
        user.user_id, payload.title)
    return SessionResponse.from_record(session)


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
) -> SessionDetailResponse:
    memory = request.app.state.container.memory
    session: ChatSession | None = memory.get_session(session_id, user.user_id)
    messages = memory.list_messages(session_id, user.user_id)
    if session is None or messages is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    summary = SessionResponse.from_record(session)
    return SessionDetailResponse(
        **summary.model_dump(),
        messages=[MessageResponse.from_record(message) for message in messages],
    )


@router.post("/stream")
async def stream_chat(
    payload: ChatStreamRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
) -> StreamingResponse:
    container: Any = request.app.state.container
    if container.memory.get_session(payload.session_id, user.user_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    try:
        container.rate_limiter.consume(user.user_id)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Request rate limit exceeded.",
            headers={
                "Retry-After": str(
                    max(1, int(exc.retry_after_seconds + 0.99))
                ),
            },
        ) from exc

    request_id = request.state.request_id
    container.memory.append_message(
        payload.session_id, user.user_id, "user", payload.message)

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in container.chat_service.stream_turn(
                request_id=request_id,
                session_id=payload.session_id,
                question=payload.message,
                user=user,
            ):
                yield encode_sse(event)
        except Exception:
            yield encode_sse(
                ActivityEvent(
                    event_type="failure",
                    request_id=request_id,
                    session_id=payload.session_id,
                    agent="api",
                    node="stream",
                    message=(
                        "The assistant could not complete this request. "
                        "Please try again."
                    ),
                    metadata={"error_code": "stream_failed"},
                )
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
