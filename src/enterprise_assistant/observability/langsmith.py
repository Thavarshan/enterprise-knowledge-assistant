"""Configure redacted LangSmith tracing for the application graph.

LangSmith traces are explicit opt-in and use a dedicated Client with inputs,
outputs, metadata, runtime details, and error strings protected before export.
"""

import logging
import os
import uuid
from typing import Any

from langsmith import Client

from enterprise_assistant.config.settings import Settings

logger = logging.getLogger(__name__)


def _redact_payload(payload: dict[str, Any]) -> dict[str, str]:
    """Replace every value in a LangSmith payload with a fixed marker.

    The client hides inputs, outputs, and metadata completely. This
    anonymizer provides defense in depth for error strings, which may contain
    provider responses, request details, or other sensitive data.

    Args:
        payload: Serialized LangSmith metadata or error mapping.

    Returns:
        A mapping with the original keys and redacted values.
    """
    return {key: "[REDACTED]" for key in payload}


def _report_trace_error(error: Exception) -> None:
    """Log LangSmith export failures without logging exception content.

    Args:
        error: Exception reported by the LangSmith client.
    """
    logger.warning(
        "LangSmith trace export failed",
        extra={"error_type": type(error).__name__},
    )


def _disable_native_tracing() -> None:
    """Disable environment-based tracing after setup is rejected.

    Remove the credentials and selector used by LangGraph's environment
    integration so rejected configuration cannot fall back to native export.
    """
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ.pop("LANGSMITH_API_KEY", None)
    os.environ.pop("LANGSMITH_WORKSPACE_ID", None)


def configure_langsmith(settings: Settings) -> bool:
    """Configure LangSmith credentials while disabling implicit tracing.

    Tracing requires both the explicit opt-in and an API key. Payload hiding
    stays enabled, and ``LANGSMITH_TRACING`` remains false. Graph tracing is
    enabled only inside the explicit context using the redacting client.

    Args:
        settings: Validated application settings.

    Returns:
        True when tracing is configured as enabled; otherwise False.
    """
    enabled = settings.langsmith_tracing and bool(settings.langsmith_api_key)
    workspace_id = settings.langsmith_workspace_id.strip()
    if enabled and workspace_id:
        try:
            uuid.UUID(workspace_id)
        except ValueError:
            logger.warning(
                "LangSmith tracing disabled: workspace ID must be a UUID"
            )
            enabled = False
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGSMITH_HIDE_INPUTS"] = "true"
    os.environ["LANGSMITH_HIDE_OUTPUTS"] = "true"
    os.environ["LANGSMITH_HIDE_METADATA"] = "true"
    if enabled:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
        if workspace_id:
            os.environ["LANGSMITH_WORKSPACE_ID"] = workspace_id
        else:
            os.environ.pop("LANGSMITH_WORKSPACE_ID", None)
    else:
        _disable_native_tracing()
    return enabled


def create_langsmith_client(settings: Settings) -> Client | None:
    """Create a LangSmith client with payload redaction enforced.

    An invalid optional workspace selector disables export without taking
    down the local API. Delivery still requires a successful external trace
    check; client construction only validates local configuration.

    Args:
        settings: Validated application settings.

    Returns:
        A redacting client when tracing is configured, or None otherwise.
    """
    if not configure_langsmith(settings):
        return None

    workspace_id = settings.langsmith_workspace_id.strip()
    try:
        return Client(
            api_key=settings.langsmith_api_key,
            workspace_id=workspace_id or None,
            hide_inputs=True,
            hide_outputs=True,
            hide_metadata=True,
            anonymizer=_redact_payload,
            omit_traced_runtime_info=True,
            tracing_error_callback=_report_trace_error,
        )
    except Exception as exc:
        _disable_native_tracing()
        logger.warning(
            "LangSmith client initialization failed",
            extra={"error_type": type(exc).__name__},
        )
        return None
