"""Keep CI and deployment authorization rules explicit and testable.

Pure policy helpers reject incomplete job results, unsafe events, disabled
opt-ins, and release commits that are no longer current on the main branch.
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
    upstream_event: str,
    upstream_branch: str,
    upstream_conclusion: str,
    manual_ci_result: str,
    deploy_enabled: bool,
    live_smoke_enabled: bool,
    release_sha: str,
    main_sha: str,
) -> list[str]:
    """Return why a release is not authorized to deploy.

    Args:
        trigger: Event that started the deployment workflow.
        ref: Git ref selected for a manual workflow run.
        upstream_event: Event that started the completed CI workflow.
        upstream_branch: Branch tested by the completed CI workflow.
        upstream_conclusion: Conclusion from the completed CI workflow.
        manual_ci_result: Result of CI invoked by a manual deployment.
        deploy_enabled: Explicit repository deployment opt-in.
        live_smoke_enabled: Explicit permission for one live chat smoke.
        release_sha: Commit approved by CI.
        main_sha: Current remote main commit.

    Returns:
        A list of blockers; an empty list authorizes deployment.
    """
    blockers: list[str] = []
    if trigger == "workflow_run":
        if upstream_event != "push" or upstream_branch != "main":
            blockers.append("Only successful pushes to main may deploy.")
        if upstream_conclusion != "success":
            blockers.append("The upstream CI workflow did not succeed.")
    elif trigger == "workflow_dispatch":
        if ref != "refs/heads/main":
            blockers.append("Manual deployments must select main.")
        if manual_ci_result != "success":
            blockers.append("CI invoked by this manual run did not succeed.")
    else:
        blockers.append("This workflow event is not a deployment trigger.")

    if not deploy_enabled:
        blockers.append("DEPLOY_ENABLED is not true.")
    if not live_smoke_enabled:
        blockers.append("RUN_LIVE_E2E_SMOKE is not true.")
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
