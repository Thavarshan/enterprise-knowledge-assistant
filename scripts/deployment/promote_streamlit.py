"""Fast-forward the Streamlit deployment branch to an approved commit.

The default Actions Git credential pushes only when the current deployment
branch is an ancestor; this helper never rewrites branch history.
"""

import os
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT_BRANCH = "deploy/streamlit"


def _git(
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run Git without shell expansion or credential output.

    Args:
        arguments: Git command arguments.
        check: Whether a non-zero status raises an exception.

    Returns:
        Captured Git output and return code.
    """
    return subprocess.run(
        ["git", *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=check,
        text=True,
        timeout=60,
    )


def _write_summary(release_sha: str, already_current: bool) -> None:
    """Record the promoted branch and exact commit in the job summary.

    Args:
        release_sha: Commit sent to Streamlit Community Cloud.
        already_current: Whether the branch already pointed to that commit.
    """
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as file:
            file.write("### Streamlit source promotion\n\n")
            file.write(f"- Branch: `{DEPLOYMENT_BRANCH}`\n")
            file.write(f"- Release: `{release_sha}`\n")
            status = "Already current" if already_current else "Fast-forwarded"
            file.write(f"- Result: {status}; no force push used.\n\n")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as file:
            file.write(f"branch_sha={release_sha}\n")


def main() -> int:
    """Fast-forward the protected deployment branch with the Actions token.

    Returns:
        Zero when the branch equals the approved release SHA.
    """
    release_sha = os.environ.get("RELEASE_SHA", "").lower()
    branch = os.environ.get("STREAMLIT_BRANCH", DEPLOYMENT_BRANCH)
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("CI_GATE_PASSED") != "true"
        or os.environ.get("DEPLOY_ENABLED", "").lower() != "true"
        or branch != DEPLOYMENT_BRANCH
        or len(release_sha) != 40
    ):
        print("Streamlit promotion is not authorized for this run.")
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
        remote = _git(
            "ls-remote",
            "origin",
            f"refs/heads/{DEPLOYMENT_BRANCH}",
            check=False,
        )
        if remote.returncode != 0:
            raise RuntimeError("Could not read the deployment branch.")
        remote_sha = remote.stdout.split(maxsplit=1)[0] if remote.stdout else ""
        if remote_sha:
            _git("fetch", "--no-tags", "origin", f"refs/heads/{branch}")
            current = _git("rev-parse", "FETCH_HEAD").stdout.strip()
            if current == release_sha:
                _write_summary(release_sha, already_current=True)
                print("Streamlit deployment branch already has this release.")
                return 0
            ancestor = _git(
                "merge-base",
                "--is-ancestor",
                current,
                release_sha,
                check=False,
            )
            if ancestor.returncode != 0:
                raise RuntimeError(
                    "The deployment branch is not an ancestor of this release."
                )
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
        _git(
            "push",
            "origin",
            f"{release_sha}:refs/heads/{DEPLOYMENT_BRANCH}",
        )
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        print(f"Streamlit branch promotion failed: {exc}")
        return 1
    _write_summary(release_sha, already_current=False)
    print(f"Fast-forwarded {DEPLOYMENT_BRANCH} to the approved release.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
