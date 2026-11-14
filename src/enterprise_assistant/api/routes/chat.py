"""Expose owner-scoped sessions and the SSE chat endpoint.

Before streaming, the route authenticates the user, verifies session
ownership, checks the input guardrail, consumes a per-user rate token, and
persists the user message. Graph activity is encoded as SSE; failures are
returned as generic events.
"""

import asyncio
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
    """Create a conversation owned by the authenticated user.

    Session data is written through the configured synchronous store in a
    worker thread, then converted to the public response schema.

    Args:
        payload: Optional title validated by the request schema.
        request: Request containing the shared service container.
        user: Authenticated owner resolved by FastAPI.

    Returns:
        The newly created session identifier, title, and timestamp.
    """
    session = await asyncio.to_thread(
        request.app.state.container.memory.create_session,
        user.user_id,
        payload.title,
    )
    return SessionResponse.from_record(session)


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
) -> SessionDetailResponse:
    """Return a session and its messages only to its owner.

    The store checks ownership on both the session lookup and history
    query. Nonexistent and foreign-owned sessions share the same 404
    response to avoid disclosing whether another user's ID exists.

    Args:
        session_id: Session identifier from the URL.
        request: Request containing the shared service container.
        user: Authenticated owner resolved by FastAPI.

    Returns:
        Public session details and ordered messages.

    Raises:
        HTTPException: 404 when the session is absent or not owned by
            this user.
    """
    memory = request.app.state.container.memory
    session, messages = await asyncio.gather(
        asyncio.to_thread(memory.get_session, session_id, user.user_id),
        asyncio.to_thread(memory.list_messages, session_id, user.user_id),
    )
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
    """Validate ownership and limits before starting SSE output.

    The route checks the owner-scoped session and input guardrail, consumes
    one per-user token, and persists the user message before constructing
    the stream. It then relays service activity as server-sent events.
    Stream-time failures produce a generic failure event; the user message
    remains persisted if graph execution fails.

    Args:
        payload: Validated session identifier and nonblank message.
        request: Request supplying the service container and request ID.
        user: Authenticated user and trusted role.

    Returns:
        StreamingResponse using text/event-stream.

    Raises:
        HTTPException: 400 for rejected input, 404 for a foreign or missing
            session, or 429 when the process-local token bucket is empty.

    Security:
        Ownership, input guardrails, and rate checks happen before message
        persistence and graph execution; client roles are not consulted.
    """
    container: Any = request.app.state.container
    session = await asyncio.to_thread(
        container.memory.get_session,
        payload.session_id,
        user.user_id,
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    guardrail_decision = await container.input_guardrail.inspect(
        payload.message,
        user_id=user.user_id,
    )
    if not guardrail_decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=guardrail_decision.message,
        )
    # Ownership and quota checks precede persistence and graph side effects.
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
    await asyncio.to_thread(
        container.memory.append_message,
        payload.session_id,
        user.user_id,
        "user",
        payload.message,
    )

    async def event_stream() -> AsyncIterator[str]:
        """Relay graph activity and mask unexpected stream failures.

        Each service event is encoded as an SSE record. An exception
        after response headers have been sent cannot change the HTTP
        status, so the generator emits a generic failure event instead.

        Yields:
            Encoded SSE strings for activity and any terminal failure.
        """
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
