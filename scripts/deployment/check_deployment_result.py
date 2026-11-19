"""Fail and summarize releases with any incomplete deployment stage.

The result includes only configured URLs, release identity, and job status;
it never includes provider response bodies or credential values.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

from scripts.deployment.policy import failed_ci_jobs


def main() -> int:
    """Require success from every job in the enabled production release.

    Returns:
        Zero only when every deployment and smoke job succeeded.
    """
    try:
        jobs: dict[str, Any] = json.loads(os.environ["DEPLOY_NEEDS_JSON"])
    except (KeyError, json.JSONDecodeError):
        print("Deployment job results were not available.")
        return 1
    results = {
        name: (
            str(details.get("result", "missing"))
            if isinstance(details, dict)
            else "missing"
        )
        for name, details in jobs.items()
    }
    failures = failed_ci_jobs(results)
    if failures:
        details = ", ".join(
            f"{name}={result}" for name, result in sorted(failures.items())
        )
        message = f"Deployment is not successful: {details}"
        print(message)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with Path(summary).open("a", encoding="utf-8") as file:
                file.write(f"## Deployment FAILED\n\n{message}\n")
        return 1
    release_sha = os.environ.get("RELEASE_SHA", "unknown")
    urls = (
        (
            "Viridian API and frontend",
            os.environ.get("CLOUDFLARE_API_URL", ""),
        ),
        (
            "Viridian D1 gateway",
            os.environ.get("CLOUDFLARE_D1_GATEWAY_URL", ""),
        ),
    )
    print(f"Deployment and API smoke checks passed for {release_sha}.")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as file:
            file.write("## Deployment SUCCESSFUL\n\n")
            file.write(f"- Release SHA: `{release_sha}`\n")
            for label, url in urls:
                file.write(f"- {label}: {url}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
