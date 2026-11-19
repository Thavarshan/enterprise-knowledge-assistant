"""Render and validate the free-tier Viridian Python Worker configuration."""

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKER_ROOT = REPOSITORY_ROOT
TEMPLATE = REPOSITORY_ROOT / "wrangler.jsonc"
DEPLOY_CONFIG = REPOSITORY_ROOT / "wrangler.deploy.jsonc"
API_HOST = "viridian.thavarshan.workers.dev"
D1_HOST = "viridian-d1-gateway.thavarshan.workers.dev"


def _require_origin(name: str, expected_host: str) -> str:
    """Return a configured HTTPS origin only when its hostname is expected."""
    value = os.environ.get(name, "").strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != expected_host
        or parsed.path not in {"", "/"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{name} must be the expected HTTPS origin.")
    return value


def render_wrangler_config() -> Path:
    """Render the private config with the approved account and release.

    The checked-in file contains only the free Workers, D1, and static asset
    bindings. Secrets are supplied separately to Wrangler.
    """
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    database_id = os.environ.get("CLOUDFLARE_D1_DATABASE_ID", "")
    release_sha = os.environ.get("RELEASE_SHA", "").lower()
    if not re.fullmatch(r"[0-9a-fA-F]{32}", account_id):
        raise ValueError("CLOUDFLARE_ACCOUNT_ID must be 32 hex characters.")
    if not re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        database_id,
    ):
        raise ValueError("CLOUDFLARE_D1_DATABASE_ID must be a UUID.")
    if not re.fullmatch(r"[0-9a-f]{40}", release_sha):
        raise ValueError("RELEASE_SHA must be a full lowercase Git SHA.")

    api_origin = _require_origin("CLOUDFLARE_API_URL", API_HOST)
    d1_origin = _require_origin("CLOUDFLARE_D1_GATEWAY_URL", D1_HOST)
    config: dict[str, Any] = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    if config.get("name") != "viridian":
        raise ValueError("The Python Worker name must remain viridian.")
    if config.get("vars", {}).get("D1_API_URL") != d1_origin:
        raise ValueError("The checked-in D1 gateway origin changed.")

    config["account_id"] = account_id
    config["vars"]["APP_RELEASE_SHA"] = release_sha
    config["vars"]["D1_API_URL"] = d1_origin
    config["vars"]["CORS_ORIGINS"] = json.dumps([api_origin])
    DEPLOY_CONFIG.write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
    )
    return DEPLOY_CONFIG


def main() -> int:
    """Render the private Python Worker configuration for a CI release."""
    try:
        path = render_wrangler_config()
    except (OSError, ValueError) as exc:
        print(f"Viridian API configuration failed: {exc}")
        return 1
    print(f"Prepared private Cloudflare API config: {path.name}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())

