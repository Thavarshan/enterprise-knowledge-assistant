"""Attach a validated request identifier to API execution and logs.

Safe caller-provided IDs are preserved; malformed or oversized values are
replaced with UUIDs. A context variable correlates logs during the request,
and middleware resets it in `finally` to avoid leaking context between
requests handled by the same process.
"""

import re
import time
import uuid
from logging import getLogger

from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.requests import Request
from starlette.responses import Response

from enterprise_assistant.observability.logging import request_id_context

logger = getLogger(__name__)
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Correlate each HTTP request with logs and responses.

    A caller-supplied identifier is accepted only when it matches a bounded
    safe character set; otherwise a UUID is generated. The context variable
    is reset after downstream execution, including when request processing
    raises.

    Concurrency:
        Context variables isolate request IDs across async task contexts.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Attach correlation, time downstream work, and reset context.

        The middleware stores the request ID on request state, passes the
        request to the next handler and adds the ID to successful
        responses. The finally block resets logging context even when
        the handler fails.

        Args:
            request: Incoming Starlette request.
            call_next: Downstream ASGI request handler.

        Returns:
            The downstream response with an X-Request-ID header.

        Concurrency:
            The context token is local to this request task and is always
            reset in a finally block.
        """
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if _SAFE_REQUEST_ID.fullmatch(
            supplied) else str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "HTTP request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(
                        (time.perf_counter() - started) * 1000, 2
                    ),
                },
            )
            return response
        finally:
            request_id_context.reset(token)
