"""Configure LangSmith agent-addressed tracing and secret protection.

Application traces include execution inputs, outputs, metadata, runtime
details, and errors. Credential-like values are anonymized before export.
"""

import logging
import os
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from langsmith import AgentAddress, Client, agent_address
from langsmith.anonymizer import create_secret_anonymizer

from enterprise_assistant.config.settings import Settings

logger = logging.getLogger(__name__)

_LEGACY_DESTINATIONS = (
    "LANGSMITH_PROJECT",
    "LANGCHAIN_PROJECT",
    "LANGCHAIN_SESSION",
)
_SECRET_ANONYMIZER = create_secret_anonymizer()


def sanitize_trace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep trace content while replacing recognized credential patterns.

    The LangSmith SDK calls its anonymizer for nested inputs, outputs,
    metadata, and errors before uploading a run.

    Args:
        payload: Serialized inputs, outputs, metadata, or the wrapped trace error.

    Returns:
        The original trace structure with recognized secrets anonymized.
    """
    sanitized = _SECRET_ANONYMIZER(payload)
    return sanitized if isinstance(sanitized, dict) else payload


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
    for name in (
        "LANGSMITH_HIDE_INPUTS",
        "LANGSMITH_HIDE_OUTPUTS",
        "LANGSMITH_HIDE_METADATA",
    ):
        os.environ[name] = "true"


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

    _disable_tracing()

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
    for name in (
        "LANGSMITH_HIDE_INPUTS",
        "LANGSMITH_HIDE_OUTPUTS",
        "LANGSMITH_HIDE_METADATA",
    ):
        os.environ[name] = "false"
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
    """Create a client that exports informative traces with secret scrubbing.

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
            hide_inputs=False,
            hide_outputs=False,
            hide_metadata=False,
            anonymizer=sanitize_trace_payload,
            omit_traced_runtime_info=False,
            tracing_error_callback=tracing_error_callback,
        )
    except Exception as exc:
        logger.error(
            "LangSmith client initialization failed",
            extra={"error_type": type(exc).__name__},
        )
        _disable_tracing()
        return None
