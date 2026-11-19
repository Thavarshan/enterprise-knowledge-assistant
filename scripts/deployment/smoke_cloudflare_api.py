"""Check the Viridian frontend, FastAPI routes, chat, and D1 persistence.

The smoke sends synthetic messages and verifies that a response is stored.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from scripts.deployment.smoke_http import (
    SmokeCheckError,
    https_origin,
    request_json,
    write_summary,
)

USER_AGENT = "Viridian-smoke/1.0"


def _request_headers(token: str = "") -> dict[str, str]:
    """Build request headers with an optional bearer token.

    Args:
        token: Access token to include when authenticating the request.

    Returns:
        Headers containing the smoke user agent and optional authorization.
    """
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _check_static_asset(url: str, expected_text: str) -> None:
    """Fetch an asset and confirm it contains an expected marker.

    Args:
        url: Deployed asset URL to request.
        expected_text: Text that must appear in the decoded response body.

    Raises:
        SmokeCheckError: The asset is unavailable or contains unexpected data.
    """
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(200_000).decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SmokeCheckError(
            "A Viridian frontend asset could not be reached."
        ) from exc
    if expected_text not in body:
        raise SmokeCheckError("The deployed frontend asset was unexpected.")


def _check_chat_stream(url: str, token: str, payload: dict[str, str]) -> None:
    """Consume a chat event stream and require a completed turn.

    Args:
        url: Chat streaming endpoint URL.
        token: Analyst access token.
        payload: Session ID and synthetic user message.

    Raises:
        SmokeCheckError: The stream fails or omits its completion event.
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            **_request_headers(token),
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    event_types: set[str] = set()
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            if response.status != 200:
                raise SmokeCheckError("The Viridian chat stream did not start.")
            for line in response:
                if not line.startswith(b"data:"):
                    continue
                try:
                    event = json.loads(line[5:].strip())
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise SmokeCheckError(
                        "The Viridian chat stream contained invalid events."
                    ) from exc
                if isinstance(event, dict):
                    event_types.add(str(event.get("event_type", "")))
    except urllib.error.HTTPError as exc:
        raise SmokeCheckError(
            f"The Viridian chat endpoint returned HTTP {exc.code}."
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SmokeCheckError(
            "The Viridian chat stream could not complete."
        ) from exc
    if "failure" in event_types or "completed" not in event_types:
        raise SmokeCheckError("The Viridian chat turn did not complete.")


def run_smoke() -> None:
    """Exercise the deployed UI/API and persist one synthetic chat turn.

    Raises:
        SmokeCheckError: Any remote check or persistence assertion fails.
    """
    api_url = https_origin(
        os.environ.get("CLOUDFLARE_API_URL", ""),
        "CLOUDFLARE_API_URL",
    )
    release_sha = os.environ.get("RELEASE_SHA", "").lower()
    analyst_password = os.environ.get("SMOKE_ANALYST_PASSWORD", "")
    viewer_password = os.environ.get("SMOKE_VIEWER_PASSWORD", "")
    if not all((release_sha, analyst_password, viewer_password)):
        raise SmokeCheckError("Viridian API smoke credentials are missing.")

    assets_ready = False
    for attempt in range(10):
        try:
            _check_static_asset(api_url + "/", "Viridian")
            assets_ready = True
            break
        except SmokeCheckError:
            if attempt == 9:
                raise
            time.sleep(5)
    if not assets_ready:
        raise SmokeCheckError("Viridian frontend assets did not become ready.")
    _check_static_asset(api_url + "/app.js", "chat/stream")
    _check_static_asset(api_url + "/styles.css", ".shell")

    _, health = request_json(f"{api_url}/health")
    if health.get("status") != "ok":
        raise SmokeCheckError("Viridian health did not report ready.")
    _, version = request_json(f"{api_url}/version")
    if (
        version.get("release_sha") != release_sha
        or version.get("mode") != "mock"
        or version.get("provider") != "mock"
        or version.get("retrieval") != "fixtures"
    ):
        raise SmokeCheckError(
            "Viridian is not serving the approved free release."
        )
    _, readiness = request_json(f"{api_url}/ready")
    if readiness.get("status") != "ready":
        raise SmokeCheckError("Viridian D1 readiness did not pass.")

    _, token_payload = request_json(
        f"{api_url}/api/v1/auth/token",
        method="POST",
        payload={"username": "analyst", "password": analyst_password},
        expected_status=200,
    )
    analyst_token = str(token_payload.get("access_token", ""))
    if not analyst_token:
        raise SmokeCheckError("Viridian did not issue an analyst token.")
    _, identity = request_json(
        f"{api_url}/api/v1/me",
        headers=_request_headers(analyst_token),
    )
    if (
        identity.get("user_id") != "analyst"
        or identity.get("role") != "analyst"
    ):
        raise SmokeCheckError("Viridian analyst identity was unexpected.")

    _, viewer_payload = request_json(
        f"{api_url}/api/v1/auth/token",
        method="POST",
        payload={"username": "viewer", "password": viewer_password},
        expected_status=200,
    )
    viewer_token = str(viewer_payload.get("access_token", ""))
    if not viewer_token:
        raise SmokeCheckError("Viridian did not issue a viewer token.")

    _, session = request_json(
        f"{api_url}/api/v1/chat/sessions",
        method="POST",
        headers=_request_headers(analyst_token),
        payload={"title": f"Smoke {release_sha[:12]}"},
        expected_status=201,
    )
    session_id = str(session.get("session_id", ""))
    if not session_id:
        raise SmokeCheckError("Viridian did not create a chat session.")
    request_json(
        f"{api_url}/api/v1/chat/sessions/"
        f"{urllib.parse.quote(session_id, safe='')}",
        headers=_request_headers(viewer_token),
        expected_status=404,
    )
    _check_chat_stream(
        f"{api_url}/api/v1/chat/stream",
        analyst_token,
        {
            "session_id": session_id,
            "message": "Summarize the payment incident recovery steps.",
        },
    )
    _, detail = request_json(
        f"{api_url}/api/v1/chat/sessions/"
        f"{urllib.parse.quote(session_id, safe='')}",
        headers=_request_headers(analyst_token),
    )
    messages: list[dict[str, Any]] = detail.get("messages", [])
    if not any(message.get("role") == "assistant" for message in messages):
        raise SmokeCheckError("Viridian did not persist the assistant answer.")

    write_summary(
        "Viridian frontend and API",
        [
            f"URL: {api_url}",
            f"Release: {release_sha}",
            "Static HTML, JavaScript, and CSS assets loaded.",
            "Health, release identity, mock-mode, and D1 readiness passed.",
            "Analyst login, viewer isolation, chat streaming, and D1 "
            "persistence passed.",
        ],
    )
    print("Viridian frontend, API, chat, and D1 smoke passed.")


def main() -> int:
    """Run API smoke checks with concise, safe diagnostics.

    Returns:
        Zero when every remote check passes, otherwise one.
    """
    try:
        run_smoke()
    except SmokeCheckError as exc:
        write_summary("Viridian API FAILED", [str(exc)])
        print(f"Viridian API smoke failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
