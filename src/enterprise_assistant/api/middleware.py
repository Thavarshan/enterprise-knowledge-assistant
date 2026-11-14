"""Request ID middleware for logs, response headers, and graph runs."""

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
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
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
