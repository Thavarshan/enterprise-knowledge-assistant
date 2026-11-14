"""Report an explicit blocked or ready deployment authorization state.

The result is written to GitHub's job output and summary without exposing
secrets, and blocked runs return a failing status before deployment jobs.
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
    """Evaluate the workflow event, CI result, opt-ins, and release SHA.

    Returns:
        Zero when readiness was evaluated, including an explicit block.
    """
    blockers = deployment_blockers(
        trigger=os.environ.get("TRIGGER", ""),
        ref=os.environ.get("GITHUB_REF", ""),
        upstream_event=os.environ.get("UPSTREAM_EVENT", ""),
        upstream_branch=os.environ.get("UPSTREAM_BRANCH", ""),
        upstream_conclusion=os.environ.get("UPSTREAM_CONCLUSION", ""),
        manual_ci_result=os.environ.get("MANUAL_CI_RESULT", ""),
        deploy_enabled=os.environ.get("DEPLOY_ENABLED", "").lower()
        == "true",
        live_smoke_enabled=os.environ.get(
            "RUN_LIVE_E2E_SMOKE", ""
        ).lower() == "true",
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
        return 1
    else:
        _write_summary(
            "Deployment READY",
            ["CI passed; explicit deployment and live-smoke opt-ins are set."],
        )
        print("Deployment is ready to start.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
