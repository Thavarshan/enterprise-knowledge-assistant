"""Verify Vercel health, release identity, auth, and D1-backed sessions.

Only synthetic test identities are used; error output omits tokens and remote
response content while checking owner isolation across separate requests.
"""

import os
import sys
import time

from scripts.deployment.smoke_http import (
    SmokeCheckError,
    https_origin,
    request_json,
    write_summary,
)


def _login(
    origin: str,
    username: str,
    password: str,
    *,
    headers: dict[str, str] | None = None,
) -> str:
    """Issue one smoke-test token without logging the credential or token.

    Args:
        origin: Public API origin.
        username: Configured synthetic user ID.
        password: Environment-provided smoke credential.
        headers: Optional deployment-protection bypass header.

    Returns:
        Signed access token used only by this script process.
    """
    _, token = request_json(
        f"{origin}/api/v1/auth/token",
        method="POST",
        headers=headers,
        payload={"username": username, "password": password},
    )
    access_token = token.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise SmokeCheckError("Authentication returned no access token.")
    return access_token


def run_smoke() -> None:
    """Check live mode, API schemas, identity, ownership, and session reads.

    Raises:
        SmokeCheckError: A required live API or persistence check fails.
    """
    origin = https_origin(
        os.environ.get("VERCEL_URL", ""),
        "VERCEL_URL",
    )
    expected_sha = os.environ.get("RELEASE_SHA", "").lower()
    passwords = {
        "analyst": os.environ.get("SMOKE_ANALYST_PASSWORD", ""),
        "viewer": os.environ.get("SMOKE_VIEWER_PASSWORD", ""),
    }
    bypass_secret = os.environ.get(
        "VERCEL_AUTOMATION_BYPASS_SECRET",
        "",
    )
    if not expected_sha or any(not value for value in passwords.values()):
        raise SmokeCheckError(
            "Release SHA or synthetic smoke credentials missing."
        )
    bypass_headers = (
        {"x-vercel-protection-bypass": bypass_secret}
        if bypass_secret
        else {}
    )

    version: dict[str, object] = {}
    for attempt in range(40):
        try:
            _, response = request_json(
                f"{origin}/version",
                headers=bypass_headers,
            )
            if response.get("release_sha") == expected_sha:
                version = response
                break
        except SmokeCheckError:
            pass
        if attempt < 39:
            time.sleep(15)
    else:
        raise SmokeCheckError(
            "Vercel did not serve the approved release SHA in time."
        )

    _, health = request_json(f"{origin}/health", headers=bypass_headers)
    _, readiness = request_json(
        f"{origin}/ready",
        headers=bypass_headers,
    )
    if health.get("status") != "ok":
        raise SmokeCheckError("The Vercel health response was unexpected.")
    if readiness.get("status") != "ready":
        raise SmokeCheckError("The Vercel readiness response was unexpected.")
    if version.get("release_sha") != expected_sha:
        raise SmokeCheckError("The Vercel deployment serves a different SHA.")
    if version.get("mode") != "live":
        raise SmokeCheckError("The Vercel deployment is running in mock mode.")

    analyst_token = _login(
        origin,
        "analyst",
        passwords["analyst"],
        headers=bypass_headers,
    )
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}
    _, identity = request_json(
        f"{origin}/api/v1/me",
        headers={**bypass_headers, **analyst_headers},
    )
    if identity.get("role") != "analyst":
        raise SmokeCheckError("The smoke account did not receive Analyst role.")
    _, created = request_json(
        f"{origin}/api/v1/chat/sessions",
        method="POST",
        headers={**bypass_headers, **analyst_headers},
        payload={"title": f"CI smoke {expected_sha[:12]}"},
        expected_status=201,
    )
    session_id = created.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise SmokeCheckError("Vercel did not create a smoke conversation.")
    _, first_read = request_json(
        f"{origin}/api/v1/chat/sessions/{session_id}",
        headers={**bypass_headers, **analyst_headers},
    )
    _, second_read = request_json(
        f"{origin}/api/v1/chat/sessions/{session_id}",
        headers={**bypass_headers, **analyst_headers},
    )
    if (
        first_read.get("session_id") != session_id
        or second_read.get("session_id") != session_id
        or not isinstance(second_read.get("messages"), list)
    ):
        raise SmokeCheckError(
            "Session history did not persist across requests."
        )

    viewer_token = _login(
        origin,
        "viewer",
        passwords["viewer"],
        headers=bypass_headers,
    )
    _, denied = request_json(
        f"{origin}/api/v1/chat/sessions/{session_id}",
        headers={
            **bypass_headers,
            "Authorization": f"Bearer {viewer_token}",
        },
        expected_status=404,
    )
    if denied.get("detail") != "Session not found.":
        raise SmokeCheckError("Session ownership isolation was not enforced.")

    write_summary(
        "Vercel FastAPI",
        [
            f"URL: {origin}",
            f"Release: {expected_sha}",
            "Health, D1 readiness, and live-mode checks passed.",
            "Authentication, session persistence, and owner isolation passed.",
        ],
    )
    print("Vercel health, auth, session, and ownership smoke passed.")


def main() -> int:
    """Run the Vercel smoke test and suppress remote response details.

    Returns:
        Zero only after all checks pass.
    """
    try:
        run_smoke()
    except SmokeCheckError as exc:
        write_summary("Vercel FastAPI FAILED", [str(exc)])
        print(f"Vercel smoke failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
