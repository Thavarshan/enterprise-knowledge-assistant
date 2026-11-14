"""Configure LangGraph's environment-based LangSmith tracing integration.

Tracing is enabled only when the explicit setting and API key are present.
The module sets tracing variables at application construction and does not
redact inputs or outputs; enabling it may transmit chat content and retrieved
evidence to the configured external workspace.
"""

import os

from enterprise_assistant.config.settings import Settings


def configure_langsmith(settings: Settings) -> bool:
    """Set the environment variables used by native LangSmith tracing.

    Tracing requires both the explicit opt-in and an API key. This function
    does not verify network access, workspace permissions, or trace delivery.

    Args:
        settings: Validated application settings.

    Returns:
        True when tracing is configured as enabled; otherwise False.

    Security:
        Trace payloads are not redacted here and may include chat content.
    """
    enabled = settings.langsmith_tracing and bool(settings.langsmith_api_key)
    os.environ["LANGSMITH_TRACING"] = "true" if enabled else "false"
    if enabled:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
        if settings.langsmith_workspace_id:
            os.environ["LANGSMITH_WORKSPACE_ID"] = (
                settings.langsmith_workspace_id
            )
        else:
            os.environ.pop("LANGSMITH_WORKSPACE_ID", None)
    else:
        os.environ.pop("LANGSMITH_API_KEY", None)
        os.environ.pop("LANGSMITH_WORKSPACE_ID", None)
    return enabled
