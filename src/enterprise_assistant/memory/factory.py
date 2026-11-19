"""Select the configured conversation persistence adapter.

The factory keeps deployment-specific storage choice outside API services.
"""

import os

from enterprise_assistant.config.settings import Settings
from enterprise_assistant.memory.d1 import D1SessionStore
from enterprise_assistant.memory.interfaces import SessionStore


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
        from enterprise_assistant.memory.sqlite import SQLiteSessionStore
        from enterprise_assistant.memory.sqlite_async import (
            AsyncSQLiteSessionStore,
        )

        return AsyncSQLiteSessionStore(
            SQLiteSessionStore(settings.sqlite_path)
        )
    if settings.memory_backend == "d1":
        transport = None
        if os.environ.get("CLOUDFLARE_WORKER") == "true":
            from enterprise_assistant.memory.workers_transport import (
                CloudflareFetchTransport,
            )

            transport = CloudflareFetchTransport()
        return D1SessionStore(
            settings.d1_api_url,
            settings.d1_service_token,
            settings.d1_timeout_seconds,
            transport=transport,
        )
    raise ValueError("Unsupported session store backend.")
