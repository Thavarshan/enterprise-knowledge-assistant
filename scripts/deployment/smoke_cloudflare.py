"""Verify Worker authentication and synthetic D1 persistence operations.

The checks use a dedicated owner and release-tagged synthetic rows, then
report only response status, database behavior, and the deployed SHA.
"""

import os
import sys

from scripts.deployment.cloudflare_config import DATABASE_NAME
from scripts.deployment.smoke_http import (
    SmokeCheckError,
    https_origin,
    request_json,
    write_summary,
)


def run_smoke() -> None:
    """Check health, token enforcement, and an owner-scoped D1 write/read.

    Raises:
        SmokeCheckError: A required endpoint, authorization, or D1 check fails.
    """
    worker_url = https_origin(
        os.environ.get("CLOUDFLARE_WORKER_URL", ""),
        "CLOUDFLARE_WORKER_URL",
    )
    token = os.environ.get("D1_SERVICE_TOKEN", "")
    release_sha = os.environ.get("RELEASE_SHA", "").lower()
    if not token:
        raise SmokeCheckError("D1_SERVICE_TOKEN is missing.")
    _, health = request_json(f"{worker_url}/health")
    if health.get("status") != "ok":
        raise SmokeCheckError("The Worker health response was unexpected.")
    if health.get("release_sha") != release_sha:
        raise SmokeCheckError("The Worker serves a different release SHA.")
    invalid_token_status, _ = request_json(
        f"{worker_url}/internal/ready",
        headers={"Authorization": "Bearer invalid-smoke-token"},
        expected_status=401,
    )
    auth_headers = {"Authorization": f"Bearer {token}"}
    _, ready = request_json(
        f"{worker_url}/internal/ready",
        headers=auth_headers,
    )
    if ready.get("status") != "ready":
        raise SmokeCheckError(
            "The authenticated Worker readiness check failed."
        )

    owner_id = "deployment-smoke"
    headers = {**auth_headers, "X-Owner-ID": owner_id}
    _, session = request_json(
        f"{worker_url}/v1/sessions",
        method="POST",
        headers=headers,
        payload={"title": f"CI smoke {release_sha[:12]} {DATABASE_NAME}"},
        expected_status=201,
    )
    session_id = str(session.get("session_id", ""))
    if not session_id:
        raise SmokeCheckError("The Worker did not create a smoke session.")
    content = f"synthetic deployment check {release_sha[:12]}"
    _, appended = request_json(
        f"{worker_url}/v1/sessions/{session_id}/messages",
        method="POST",
        headers=headers,
        payload={"role": "user", "content": content},
        expected_status=201,
    )
    if appended.get("content") != content:
        raise SmokeCheckError("The Worker did not persist the smoke message.")
    _, history = request_json(
        f"{worker_url}/v1/sessions/{session_id}/messages",
        headers=headers,
    )
    messages = history.get("messages", [])
    if not messages or messages[-1].get("content") != content:
        raise SmokeCheckError("The D1 smoke message could not be read back.")

    write_summary(
        "Cloudflare Worker",
        [
            f"URL: {worker_url}",
            f"Release: {release_sha}",
            "Public health and release identity passed.",
            "Authenticated readiness and D1 read/write passed.",
            f"Invalid service token returned HTTP {invalid_token_status}.",
            "Synthetic smoke session is retained; no production data was read.",
        ],
    )
    print("Cloudflare Worker auth and D1 read/write smoke passed.")


def main() -> int:
    """Run the Cloudflare smoke test and report only safe diagnostics.

    Returns:
        Zero only after all checks pass.
    """
    try:
        run_smoke()
    except SmokeCheckError as exc:
        write_summary("Cloudflare Worker FAILED", [str(exc)])
        print(f"Cloudflare smoke failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
