"""Create Worker routing metadata before uploading a new script.

Wrangler uploads a script before it enables its ``workers.dev`` subdomain.
Cloudflare can briefly return a missing Worker for that immediate lookup.
"""

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

API_ORIGIN = "https://api.cloudflare.com/client/v4"


def _request_worker(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    allow_missing: bool = False,
    allow_conflict: bool = False,
) -> dict[str, Any] | None:
    """Send an authenticated Worker metadata request.

    Args:
        method: HTTP method for the Cloudflare API request.
        path: Account-scoped Worker API path.
        body: Optional JSON request body.
        allow_missing: Return ``None`` for Cloudflare's missing Worker error.
        allow_conflict: Return ``None`` when another release creates it first.

    Returns:
        Cloudflare's result object, or ``None`` for allowed absence/conflict.

    Raises:
        RuntimeError: Credentials, connectivity, or the API response is invalid.
    """
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not re.fullmatch(r"[0-9a-fA-F]{32}", account_id):
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID must be 32 hex characters.")
    if not api_token:
        raise RuntimeError("CLOUDFLARE_API_TOKEN is required.")

    headers = {"Authorization": f"Bearer {api_token}"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{API_ORIGIN}/accounts/{account_id}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read(100_000))
    except urllib.error.HTTPError as exc:
        try:
            error_payload = json.loads(exc.read(100_000))
        except (json.JSONDecodeError, OSError):
            error_payload = {}
        errors = (
            error_payload.get("errors", [])
            if isinstance(error_payload, dict)
            else []
        )
        missing_worker = any(
            isinstance(error, dict) and error.get("code") == 10007
            for error in errors
        )
        if allow_missing and exc.code == 404 and missing_worker:
            return None
        if allow_conflict and exc.code == 409:
            return None
        raise RuntimeError(
            f"Cloudflare Worker metadata request failed (HTTP {exc.code})."
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            "Cloudflare Worker metadata endpoint could not be reached."
        ) from exc

    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise RuntimeError("Cloudflare rejected the Worker metadata request.")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("Cloudflare returned invalid Worker metadata.")
    return result


def ensure_worker_registered(worker_name: str) -> bool:
    """Ensure a Worker record exists before Wrangler publishes its script.

    Args:
        worker_name: Exact Worker name declared by its Wrangler config.

    Returns:
        True when this call created Worker metadata, otherwise False.

    Raises:
        RuntimeError: The name is invalid or Cloudflare cannot create
            the record.
    """
    if not re.fullmatch(r"[a-z0-9_][a-z0-9_-]*", worker_name):
        raise RuntimeError("Worker name is not a valid Cloudflare identifier.")

    worker_path = f"/workers/workers/{worker_name}"
    existing = _request_worker("GET", worker_path, allow_missing=True)
    if existing is not None:
        if existing.get("name") != worker_name:
            raise RuntimeError("Cloudflare returned an unexpected Worker name.")
        return False

    created = _request_worker(
        "POST",
        "/workers/workers",
        body={
            "name": worker_name,
            "logpush": False,
            "observability": {"enabled": False},
            "subdomain": {"enabled": True, "previews_enabled": False},
        },
        allow_conflict=True,
    )
    if created is None:
        created = _request_worker("GET", worker_path)
    if created is None:
        raise RuntimeError("Cloudflare did not register the requested Worker.")
    if created.get("name") != worker_name:
        raise RuntimeError("Cloudflare returned an unexpected Worker name.")
    print(f"Prepared Worker routing metadata for {worker_name}.")
    return True
