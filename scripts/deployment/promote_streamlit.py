"""Verify Streamlit Community Cloud targets the approved main commit.

The current Community Cloud app follows `main` and rebuilds after a push.
This job confirms the platform is checking the same commit approved by CI.
"""

import os
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
STREAMLIT_BRANCH = "main"


def _write_summary(release_sha: str) -> None:
    """Record the expected Streamlit source branch and release commit.

    Args:
        release_sha: Full commit SHA approved by the current CI run.
    """
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write("### Streamlit source release\n\n")
            summary.write(f"- Branch: `{STREAMLIT_BRANCH}`\n")
            summary.write(f"- Release: `{release_sha}`\n")
            summary.write("- Community Cloud rebuilds from this branch.\n\n")
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write(f"branch_sha={release_sha}\n")


def main() -> int:
    """Require Streamlit's source branch to match the CI-approved SHA.

    Returns:
        Zero when the current main commit is the approved release.
    """
    release_sha = os.environ.get("RELEASE_SHA", "").lower()
    branch = os.environ.get("STREAMLIT_BRANCH", STREAMLIT_BRANCH)
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("CI_GATE_PASSED") != "true"
        or branch != STREAMLIT_BRANCH
        or len(release_sha) != 40
    ):
        print("Streamlit release is not authorized for this run.")
        return 1
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.deployment.assert_release_current",
            ],
            cwd=REPOSITORY_ROOT,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Streamlit release check failed: {exc}")
        return 1
    _write_summary(release_sha)
    print(f"Streamlit Community Cloud is tracking main at {release_sha}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
