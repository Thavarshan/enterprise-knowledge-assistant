"""Select the configured conversation persistence adapter.

The factory keeps deployment-specific storage choice outside API services.
"""

from enterprise_assistant.config.settings import Settings
from enterprise_assistant.memory.d1 import D1SessionStore
from enterprise_assistant.memory.interfaces import SessionStore
from enterprise_assistant.memory.sqlite import SQLiteSessionStore
from enterprise_assistant.memory.sqlite_async import (
    AsyncSQLiteSessionStore,
)


def create_session_store(settings: Settings) -> SessionStore:
    """Build the single store selected by validated application settings.

    Args:
        settings: Validated backend, path, URL, and credential settings.

    Returns:
        Async SQLite or D1 Worker persistence adapter.

    Raises:
        ValueError: An unsupported backend is supplied despite validation.
    """
    if settings.memory_backend == "sqlite":
        return AsyncSQLiteSessionStore(
            SQLiteSessionStore(settings.sqlite_path)
        )
    if settings.memory_backend == "d1":
        return D1SessionStore(
            settings.d1_api_url,
            settings.d1_service_token,
            settings.d1_timeout_seconds,
        )
    raise ValueError("Unsupported session store backend.")
