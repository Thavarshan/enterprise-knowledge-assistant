"""Trigger the configured Vercel production deploy hook after CI passes.

The hook URL is treated as a secret. Responses and exceptions are reduced to
safe status details before they are written to the Actions log or summary.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


def _write_summary(release_sha: str, job_id: str, state: str) -> None:
    """Record an accepted deployment without exposing its hook URL.

    Args:
        release_sha: Full commit SHA requested for deployment.
        job_id: Vercel's non-secret deployment job identifier.
        state: Vercel's deployment job state.
    """
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with Path(summary_path).open("a", encoding="utf-8") as summary:
        summary.write("## Vercel deployment triggered\n\n")
        summary.write(f"- Release: `{release_sha}`\n")
        summary.write(f"- Hook job: `{job_id or 'accepted'}`\n")
        summary.write(f"- State: `{state or 'accepted'}`\n")


def _write_output(name: str, value: str) -> None:
    """Append a single-line value to the current Actions job output.

    Args:
        name: Output name consumed by a later deployment job.
        value: Validated, non-secret output value.
    """
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write(f"{name}={value}\n")


def _validate_hook_url(value: str, project_id: str) -> None:
    """Reject a hook URL outside the configured Vercel project.

    Args:
        value: Secret URL configured for this production deployment.
        project_id: Expected Vercel project identifier.

    Raises:
        ValueError: The URL is not an HTTPS hook for the expected project.
    """
    parsed = urlsplit(value)
    segments = parsed.path.strip("/").split("/")
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.vercel.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or len(segments) != 5
        or segments[:3] != ["v1", "integrations", "deploy"]
        or segments[3] != project_id
        or not segments[4]
    ):
        raise ValueError("VERCEL_DEPLOY_HOOK is invalid for this project.")


def trigger_deployment() -> tuple[str, str]:
    """POST to Vercel's hook and return its safe job identifier and state.

    Returns:
        The Vercel job ID and state, if included in the response.

    Raises:
        RuntimeError: The hook is missing, invalid, or rejects the request.
    """
    hook_url = os.environ.get("VERCEL_DEPLOY_HOOK", "")
    project_id = os.environ.get("VERCEL_PROJECT_ID", "")
    release_sha = os.environ.get("RELEASE_SHA", "").lower()
    if not hook_url or not project_id or len(release_sha) != 40:
        raise RuntimeError("Vercel hook, project, or release SHA is missing.")
    try:
        _validate_hook_url(hook_url, project_id)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    request = urllib.request.Request(
        hook_url,
        data=b"",
        headers={"Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read())
    except (
        urllib.error.URLError,
        TimeoutError,
        ValueError,
        OSError,
    ) as exc:
        raise RuntimeError(
            "Vercel did not accept the production deployment request."
        ) from exc

    job = payload.get("job", {}) if isinstance(payload, dict) else {}
    if not isinstance(job, dict):
        raise RuntimeError("Vercel returned an invalid deployment response.")
    job_id = str(job.get("id", ""))
    state = str(job.get("state", ""))
    if state and state.lower() not in {"pending", "running", "queued"}:
        raise RuntimeError("Vercel returned an unexpected deployment state.")
    production_url = os.environ.get("VERCEL_PRODUCTION_URL", "")
    if not production_url.startswith("https://"):
        raise RuntimeError("VERCEL_PRODUCTION_URL is not configured.")
    _write_output("production_url", production_url.rstrip("/"))
    _write_summary(release_sha, job_id, state)
    return job_id, state


def main() -> int:
    """Trigger one production deployment while suppressing remote details.

    Returns:
        Zero only after Vercel accepts the request.
    """
    try:
        job_id, state = trigger_deployment()
    except RuntimeError as exc:
        print(f"Vercel deploy hook failed: {exc}")
        return 1
    print(
        "Vercel accepted the production deployment request "
        f"(job {job_id or 'accepted'}, state {state or 'accepted'})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
