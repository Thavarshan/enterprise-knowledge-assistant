"""Emit structured JSON logs with request correlation.

The formatter serializes a small allowlist of operational fields and omits
request bodies, credentials, tokens, and document contents. Middleware
provides the request context and resets it after each request.
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    """Format selected operational log fields as JSON.

    The formatter uses an allowlist rather than serializing arbitrary record
    attributes. It includes request correlation and omits request bodies,
    credentials, tokens, and document contents.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a log record with the approved operational fields.

        The active request context supplies a correlation ID when the record
        does not carry one directly.

        Args:
            record: Standard logging record to format.

        Returns:
            One JSON object as a string.
        """
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(
                record, "request_id", request_id_context.get()
            ),
        }
        for field in (
            "method",
            "path",
            "status_code",
            "duration_ms",
            "error_type",
            "missing_settings",
            "tracing_enabled",
            "mock_mode",
        ):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    """Replace root handlers with the structured JSON formatter.

    Args:
        level: Logging level name applied to the root logger.

    Side Effects:
        Clears existing root handlers and installs one stream handler.
    """
    root = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
