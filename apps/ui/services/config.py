"""Resolve deployment-safe configuration for the Streamlit presentation app.

The frontend receives only the public FastAPI base URL. Backend provider,
storage, and authentication credentials stay outside Streamlit's runtime.
"""

from collections.abc import Mapping
from urllib.parse import urlsplit

PUBLIC_API_BASE_URL = "https://viridian.vercel.app"


def resolve_api_base_url(
    environment: Mapping[str, str],
    secrets: Mapping[str, object],
    *,
    default: str = PUBLIC_API_BASE_URL,
) -> str:
    """Select and validate the configured public FastAPI URL.

    Process environment values take precedence over Streamlit secrets. The
    fallback points new deployments at the public API. Local `.env` and
    Docker Compose settings override it with their respective API addresses.

    Args:
        environment: Process environment mapping.
        secrets: Streamlit secrets mapping, containing public settings only.
        default: API origin used when no setting is provided.

    Returns:
        Valid HTTP(S) origin without a trailing slash.

    Raises:
        ValueError: The selected value is not an absolute HTTP(S) URL.
    """
    configured = environment.get("API_BASE_URL")
    if not configured:
        secret_value = secrets.get("API_BASE_URL")
        configured = secret_value if isinstance(secret_value, str) else None
    value = (configured or default).strip().rstrip("/")
    parsed = urlsplit(value)
    try:
        has_valid_port = parsed.port is None or 1 <= parsed.port <= 65535
    except ValueError:
        has_valid_port = False
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or not has_valid_port
    ):
        raise ValueError("API_BASE_URL must be an HTTP(S) origin.")
    return value
