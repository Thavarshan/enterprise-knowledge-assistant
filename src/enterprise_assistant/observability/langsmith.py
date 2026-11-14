"""Configure LangGraph's native LangSmith tracing from application settings."""

import os

from enterprise_assistant.config.settings import Settings


def configure_langsmith(settings: Settings) -> bool:
    """Enable native graph tracing only when explicitly requested with a key."""
    enabled = settings.langsmith_tracing and bool(settings.langsmith_api_key)
    os.environ["LANGSMITH_TRACING"] = "true" if enabled else "false"
    if enabled:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    else:
        os.environ.pop("LANGSMITH_API_KEY", None)
    return enabled
