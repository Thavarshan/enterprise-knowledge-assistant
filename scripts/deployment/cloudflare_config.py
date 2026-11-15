"""Render and verify isolated Cloudflare deployment configuration.

Production account and database identifiers come only from explicit inputs;
the checked-in Wrangler template retains a non-deployable placeholder ID.
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

WORKER_NAME = "eka-d1-gateway"
DATABASE_NAME = "eka-sessions"
PLACEHOLDER_DATABASE_ID = "00000000-0000-0000-0000-000000000001"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKER_ROOT = REPOSITORY_ROOT / "infra/cloudflare/d1-gateway"
DEPLOY_CONFIG = WORKER_ROOT / "wrangler.deploy.jsonc"


def render_wrangler_config() -> Path:
    """Create a private config using explicit deployment account values.

    Returns:
        Path to the generated config ignored by Git.

    Raises:
        ValueError: A required value is missing or malformed.
    """
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    database_id = os.environ.get("CLOUDFLARE_D1_DATABASE_ID", "")
    release_sha = os.environ.get("RELEASE_SHA", "").lower()
    required = {
        "CLOUDFLARE_ACCOUNT_ID": account_id,
        "CLOUDFLARE_D1_DATABASE_ID": database_id,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(
            "Missing required Cloudflare variables: " + ", ".join(missing)
        )
    if not re.fullmatch(r"[0-9a-fA-F]{32}", account_id):
        raise ValueError("CLOUDFLARE_ACCOUNT_ID must be 32 hex characters.")
    if not re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        database_id,
    ):
        raise ValueError("CLOUDFLARE_D1_DATABASE_ID must be a UUID.")
    if database_id.lower() == PLACEHOLDER_DATABASE_ID:
        raise ValueError("The local placeholder database ID cannot deploy.")
    if not re.fullmatch(r"[0-9a-f]{40}", release_sha):
        raise ValueError("RELEASE_SHA must be a full lowercase Git SHA.")

    base = json.loads(
        (WORKER_ROOT / "wrangler.jsonc").read_text(encoding="utf-8")
    )
    base_database = base["d1_databases"][0]
    if (
        base["name"] != WORKER_NAME
        or base_database["database_name"] != DATABASE_NAME
        or base_database["binding"] != "DB"
        or base_database["database_id"] != PLACEHOLDER_DATABASE_ID
    ):
        raise ValueError(
            "The checked-in Wrangler template changed unexpectedly."
        )

    config: dict[str, Any] = dict(base)
    config["account_id"] = account_id
    config["vars"] = {"APP_RELEASE_SHA": release_sha}
    config["d1_databases"] = [{
        "binding": "DB",
        "database_name": DATABASE_NAME,
        "database_id": database_id,
        "migrations_dir": "migrations",
    }]
    DEPLOY_CONFIG.write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
    )
    return DEPLOY_CONFIG


def normalize_database_id(value: str) -> str:
    """Normalize a Cloudflare database UUID for an exact identity check.

    Args:
        value: Database ID returned by Cloudflare.

    Returns:
        Lowercase hexadecimal characters without separators.
    """
    return value.replace("-", "").lower()


def database_matches(
    payload: dict[str, Any],
    expected_name: str,
    expected_id: str,
) -> bool:
    """Confirm the Cloudflare response contains the exact dedicated D1 DB.

    Args:
        payload: Parsed response from the Cloudflare D1 list endpoint.
        expected_name: Dedicated database name for this application.
        expected_id: UUID configured for the deployment.

    Returns:
        True only when exactly one database has the expected name and ID.
    """
    if payload.get("success") is not True:
        return False
    matches = [
        database
        for database in payload.get("result", [])
        if isinstance(database, dict)
        and database.get("name") == expected_name
    ]
    if len(matches) != 1:
        return False
    actual_id = str(matches[0].get("uuid", matches[0].get("id", "")))
    return normalize_database_id(actual_id) == normalize_database_id(
        expected_id
    )


def verify_cloudflare_database() -> None:
    """Query Cloudflare and fail unless the configured D1 identity matches.

    Raises:
        ValueError: Required credentials or target metadata are missing.
        RuntimeError: Cloudflare cannot confirm the configured database.
    """
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    database_id = os.environ.get("CLOUDFLARE_D1_DATABASE_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    missing = [
        name
        for name, value in (
            ("CLOUDFLARE_ACCOUNT_ID", account_id),
            ("CLOUDFLARE_D1_DATABASE_ID", database_id),
            ("CLOUDFLARE_API_TOKEN", token),
        )
        if not value
    ]
    if missing:
        raise ValueError(
            "Missing required Cloudflare settings: " + ", ".join(missing)
        )
    query = urllib.parse.urlencode({"name": DATABASE_NAME})
    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{account_id}/d1/database?{query}"
    )
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(
            "Cloudflare D1 identity could not be verified."
        ) from exc
    if not database_matches(payload, DATABASE_NAME, database_id):
        raise RuntimeError(
            "Cloudflare did not return the dedicated D1 name and ID."
        )
    print("Cloudflare D1 name and ID match the dedicated deployment target.")


def require_gated_cloud_deployment() -> None:
    """Require the GitHub Actions gate before a remote mutation.

    Raises:
        RuntimeError: The deployment is outside an explicitly ready CI run.
    """
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Remote deployment is restricted to GitHub Actions.")
    if os.environ.get("CI_GATE_PASSED") != "true":
        raise RuntimeError("The required CI gate has not passed.")
