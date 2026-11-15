"""Keep CI and deployment authorization rules explicit and testable.

Pure policy helpers reject incomplete job results, unsafe events, and release
commits that are no longer current on the main branch.
"""

from collections.abc import Mapping


def failed_ci_jobs(results: Mapping[str, str]) -> dict[str, str]:
    """Return every required CI job that did not finish successfully.

    Args:
        results: Job names mapped to GitHub Actions result strings.

    Returns:
        Job names and their non-success results.
    """
    return {
        name: result
        for name, result in results.items()
        if result != "success"
    }


def deployment_blockers(
    *,
    trigger: str,
    ref: str,
    ci_result: str,
    release_sha: str,
    main_sha: str,
) -> list[str]:
    """Return why a release is not authorized to deploy.

    Args:
        trigger: Event that started the consolidated CI workflow.
        ref: Git ref selected for a manual workflow run.
        ci_result: Result of the mandatory CI gate in this workflow run.
        release_sha: Commit approved by CI.
        main_sha: Current remote main commit.

    Returns:
        A list of blockers; an empty list authorizes deployment.
    """
    blockers: list[str] = []
    if trigger == "push":
        if ref != "refs/heads/main":
            blockers.append("Only successful pushes to main may deploy.")
    elif trigger == "workflow_dispatch":
        if ref != "refs/heads/main":
            blockers.append("Manual deployments must select main.")
    else:
        blockers.append("This workflow event is not a deployment trigger.")

    if ci_result != "success":
        blockers.append("The mandatory CI gate did not succeed.")

    if len(release_sha) != 40 or any(
        char not in "0123456789abcdef" for char in release_sha.lower()
    ):
        blockers.append("The CI-approved release SHA is invalid.")
    if release_sha != main_sha:
        blockers.append("The CI-approved release has been superseded on main.")
    return blockers


def release_is_current(release_sha: str, main_sha: str) -> bool:
    """Return whether the release SHA still matches the main branch tip.

    Args:
        release_sha: SHA selected for deployment.
        main_sha: Current SHA advertised by origin/main.

    Returns:
        True when the selected SHA is still current.
    """
    return bool(release_sha) and release_sha == main_sha
