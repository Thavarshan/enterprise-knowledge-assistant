"""Configure LangSmith agent-addressed tracing and payload protection.

Application traces are routed to the registered agent and selected
environment. Inputs and outputs are hidden, metadata is allowlisted, and
trace errors are redacted before the SDK exports them.
"""

import logging
import os
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from langsmith import AgentAddress, Client, agent_address

from enterprise_assistant.config.settings import Settings

logger = logging.getLogger(__name__)

_LEGACY_DESTINATIONS = (
    "LANGSMITH_PROJECT",
    "LANGCHAIN_PROJECT",
    "LANGCHAIN_SESSION",
)
_SAFE_METADATA_FIELDS = frozenset(
    {
        "agent_environment",
        "agent_id",
        "agent_name",
        "graph_node",
        "langgraph_node",
        "request_id",
        "session_id",
        "status",
        "tool_name",
        "verification_id",
        "workflow",
    }
)
_SAFE_METADATA_VALUE = re.compile(r"[A-Za-z0-9_.:/ -]{1,128}\Z")
_UUID_METADATA_FIELDS = frozenset(
    {"request_id", "session_id", "verification_id"}
)


def sanitize_trace_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Keep only short, non-content correlation and routing metadata.

    LangGraph and the application may attach arbitrary metadata to spans.
    The explicit allowlist keeps known identifiers, node names, and status
    values while excluding prompts, document content, credentials, and
    unknown future fields.

    Args:
        metadata: SDK metadata mapping for one trace run.

    Returns:
        A mapping containing only safe, bounded string values.
    """
    safe_metadata: dict[str, str] = {}
    for key, value in metadata.items():
        if (
            key not in _SAFE_METADATA_FIELDS
            or not isinstance(value, str)
            or not _SAFE_METADATA_VALUE.fullmatch(value)
        ):
            continue
        if key in _UUID_METADATA_FIELDS:
            try:
                UUID(value)
            except ValueError:
                continue
        safe_metadata[key] = value
    return safe_metadata


def redact_trace_error(payload: dict[str, Any]) -> dict[str, str]:
    """Replace trace error details with a fixed marker before export.

    SDK error strings may contain provider response text or request details.
    The keys are retained for the trace schema, but their values are not.

    Args:
        payload: Serialized LangSmith error mapping.

    Returns:
        A mapping with all supplied values redacted.
    """
    return {key: "[REDACTED]" for key in payload}


def sanitize_trace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Sanitize metadata and redact trace error payloads.

    LangSmith applies its anonymizer to metadata before its metadata hiding
    callback. This combined callback preserves only allowlisted metadata and
    replaces error text with a fixed marker.

    Args:
        payload: Serialized metadata or the wrapped trace error.

    Returns:
        A sanitized metadata mapping or a redacted error mapping.
    """
    if "error" in payload:
        return redact_trace_error(payload)
    return sanitize_trace_metadata(payload)


def report_trace_error(error: Exception) -> None:
    """Log an export failure without including exception text or secrets.

    Args:
        error: Exception reported by the LangSmith SDK.
    """
    logger.warning(
        "LangSmith trace export failed",
        extra={"error_type": type(error).__name__},
    )


def _disable_tracing() -> None:
    """Disable SDK tracing and remove its process-level API key.

    No implicit LangGraph integration should export data after configuration
    has been disabled or rejected.
    """
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ.pop("LANGSMITH_API_KEY", None)


def configure_langsmith(settings: Settings) -> bool:
    """Load agent destination and credentials before clients are created.

    Agent addressing pairs the registered agent ID with an environment. It
    is independent of project names and workspace IDs. Old project/session
    destination variables are removed to prevent the SDK from overriding
    the agent address.

    Args:
        settings: Environment-backed application configuration.

    Returns:
        True when the required LangSmith configuration is valid and enabled.
    """
    for name in _LEGACY_DESTINATIONS:
        os.environ.pop(name, None)

    for name in (
        "LANGSMITH_HIDE_INPUTS",
        "LANGSMITH_HIDE_OUTPUTS",
        "LANGSMITH_HIDE_METADATA",
    ):
        os.environ[name] = "true"

    if not settings.langsmith_tracing:
        _disable_tracing()
        return False

    missing = [
        name
        for name, value in (
            ("LANGSMITH_API_KEY", settings.langsmith_api_key),
            ("LANGSMITH_ENDPOINT", settings.langsmith_endpoint),
            ("LANGSMITH_AGENT_ID", settings.langsmith_agent_id),
            (
                "LANGSMITH_AGENT_ENVIRONMENT",
                settings.langsmith_agent_environment,
            ),
        )
        if not value.strip()
    ]
    endpoint = urlsplit(settings.langsmith_endpoint)
    endpoint_is_valid = endpoint.scheme == "https" and bool(endpoint.netloc)
    if missing or not endpoint_is_valid:
        if not endpoint_is_valid:
            missing.append("valid HTTPS LANGSMITH_ENDPOINT")
        logger.error(
            "LangSmith tracing is enabled but configuration is invalid",
            extra={"missing_settings": ", ".join(missing)},
        )
        _disable_tracing()
        return False

    try:
        create_langsmith_address(settings)
    except (TypeError, ValueError) as exc:
        logger.error(
            "LangSmith agent address is invalid",
            extra={"error_type": type(exc).__name__},
        )
        _disable_tracing()
        return False

    # Agent ID + environment routes each run. This is not a project ID or
    # workspace ID, and the agent must already exist in the LangSmith UI.
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    os.environ["LANGSMITH_AGENT_ID"] = settings.langsmith_agent_id
    os.environ["LANGSMITH_AGENT_ENVIRONMENT"] = (
        settings.langsmith_agent_environment
    )
    return True


def create_langsmith_address(settings: Settings) -> AgentAddress | None:
    """Build the explicit agent/environment destination for a trace.

    Args:
        settings: Environment-backed application configuration.

    Returns:
        Agent address when both destination values are set, otherwise None.
    """
    if (
        not settings.langsmith_agent_id
        or not settings.langsmith_agent_environment
    ):
        return None
    return agent_address(
        settings.langsmith_agent_id,
        settings.langsmith_agent_environment,
    )


def create_langsmith_client(
    settings: Settings,
    *,
    tracing_error_callback: Callable[[Exception], None] = report_trace_error,
) -> Client | None:
    """Create a client that exports only redacted, allowlisted trace data.

    The explicit client protects application traces even if other SDK
    tracing integrations exist in the process. Initialization failures are
    logged and return None so ordinary API requests can continue.

    Args:
        settings: Environment-backed application configuration.
        tracing_error_callback: Safe callback for asynchronous export errors.

    Returns:
        Configured LangSmith client, or None when tracing is disabled or
        initialization fails.
    """
    if not configure_langsmith(settings):
        return None

    try:
        return Client(
            api_url=settings.langsmith_endpoint,
            api_key=settings.langsmith_api_key,
            hide_inputs=True,
            hide_outputs=True,
            hide_metadata=sanitize_trace_metadata,
            anonymizer=sanitize_trace_payload,
            omit_traced_runtime_info=True,
            tracing_error_callback=tracing_error_callback,
        )
    except Exception as exc:
        logger.error(
            "LangSmith client initialization failed",
            extra={"error_type": type(exc).__name__},
        )
        _disable_tracing()
        return None
