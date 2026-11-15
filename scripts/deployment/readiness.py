"""Report a blocked or ready deployment authorization state.

The result is written to GitHub's job output and summary without exposing
secrets. Successful CI on the current main commit authorizes deployment.
"""

import os
import sys
from pathlib import Path

from scripts.deployment.policy import deployment_blockers


def _write_output(name: str, value: str) -> None:
    """Append one output value for the current GitHub Actions job.

    Args:
        name: GitHub output identifier.
        value: Single-line output value.
    """
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write(f"{name}={value}\n")


def _write_summary(title: str, details: list[str]) -> None:
    """Append a human-readable readiness result without secret values.

    Args:
        title: Short readiness heading.
        details: Safe, non-sensitive details for the workflow summary.
    """
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with Path(summary_path).open("a", encoding="utf-8") as summary:
        summary.write(f"## {title}\n\n")
        if details:
            summary.write("\n".join(f"- {item}" for item in details))
            summary.write("\n")


def main() -> int:
    """Evaluate the workflow event, CI result, and release SHA.

    Returns:
        Zero when readiness was evaluated, including a safe block.
    """
    blockers = deployment_blockers(
        trigger=os.environ.get("TRIGGER", ""),
        ref=os.environ.get("GITHUB_REF", ""),
        ci_result=os.environ.get("CI_RESULT", ""),
        release_sha=os.environ.get("RELEASE_SHA", "").lower(),
        main_sha=os.environ.get("CURRENT_MAIN_SHA", "").lower(),
    )
    allowed = not blockers
    _write_output("run_deployment", str(allowed).lower())
    _write_output("release_sha", os.environ.get("RELEASE_SHA", ""))
    if blockers:
        _write_summary("Deployment BLOCKED", blockers)
        print("Deployment BLOCKED:")
        for blocker in blockers:
            print(f"- {blocker}")
        return 0
    else:
        _write_summary(
            "Deployment READY",
            ["CI passed; the current main commit is authorized to deploy."],
        )
        print("Deployment is ready to start.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
