"""Provide safe HTTP and summary helpers for deployment smoke tests.

Requests use bounded timeouts and suppress response bodies on failures so
provider diagnostics and returned credentials cannot enter Actions logs.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class SmokeCheckError(RuntimeError):
    """Describe a failed smoke assertion without provider response bodies.

    Callers use this type for safe, concise workflow diagnostics.
    """


def https_origin(value: str, label: str) -> str:
    """Validate and normalize one public HTTPS origin.

    Args:
        value: Configured URL or hostname.
        label: Safe setting name used in failure text.

    Returns:
        HTTPS origin without a trailing slash.

    Raises:
        SmokeCheckError: The configured value is not a public HTTPS origin.
    """
    candidate = value.strip()
    if not candidate.startswith(("https://", "http://")):
        candidate = f"https://{candidate}"
    parsed = urllib.parse.urlsplit(candidate)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise SmokeCheckError(f"{label} must be a public HTTPS origin.")
    return candidate.rstrip("/")


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    expected_status: int = 200,
) -> tuple[int, dict[str, Any]]:
    """Make a bounded JSON request and suppress remote response details.

    Args:
        url: Full request URL.
        method: HTTP method.
        headers: Optional HTTP headers.
        payload: Optional JSON object body.
        expected_status: Status required for this request.

    Returns:
        Response status and a parsed object, or an empty object.

    Raises:
        SmokeCheckError: Network, JSON, or expected-status validation fails.
    """
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.status
            response_body = response.read()
    except urllib.error.HTTPError as response:
        status = response.code
        response_body = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SmokeCheckError(
            "A deployment endpoint could not be reached."
        ) from exc
    if status != expected_status:
        raise SmokeCheckError(
            f"Endpoint returned HTTP {status}; expected {expected_status}."
        )
    if not response_body:
        return status, {}
    try:
        result = json.loads(response_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SmokeCheckError("An endpoint returned invalid JSON.") from exc
    if not isinstance(result, dict):
        raise SmokeCheckError("An endpoint returned an unexpected schema.")
    return status, result


def write_summary(title: str, details: list[str]) -> None:
    """Append a safe component result to the current GitHub job summary.

    Args:
        title: Summary heading.
        details: Non-sensitive result details.
    """
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with Path(summary_path).open("a", encoding="utf-8") as summary:
        summary.write(f"### {title}\n\n")
        summary.write("\n".join(f"- {item}" for item in details))
        summary.write("\n\n")
