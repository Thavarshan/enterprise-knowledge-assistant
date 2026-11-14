"""Build, stage, promote, and record Vercel deployments through its CLI.

The CLI output is captured so tokens and raw platform errors stay out of job
logs; promotion is permitted only after candidate smoke and SHA freshness.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
URL_PATTERN = re.compile(r"https://[A-Za-z0-9.-]+\.vercel\.app")


def _cli(arguments: list[str], *, timeout: int = 900) -> str:
    """Run the pinned Vercel CLI while keeping token values out of logs.

    Args:
        arguments: CLI arguments excluding shared token and team scope.
        timeout: Maximum time to wait for the command.

    Returns:
        Captured standard output for safe URL extraction.

    Raises:
        RuntimeError: Vercel credentials are absent or the CLI fails.
    """
    token = os.environ.get("VERCEL_TOKEN", "")
    scope = os.environ.get("VERCEL_ORG_ID", "")
    if not token or not scope:
        raise RuntimeError("VERCEL_TOKEN or VERCEL_ORG_ID is missing.")
    command = [
        "vercel",
        *arguments,
        "--scope",
        scope,
        "--token",
        token,
    ]
    try:
        result = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            "Vercel CLI could not complete the operation."
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(
            f"Vercel CLI operation failed with exit {result.returncode}."
        )
    return result.stdout


def _write_output(name: str, value: str) -> None:
    """Append a single-line output for later deployment jobs.

    Args:
        name: GitHub Actions output name.
        value: Safe URL or deployment reference.
    """
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as file:
            file.write(f"{name}={value}\n")


def _write_summary(title: str, details: list[str]) -> None:
    """Write a deployment record without exposing environment values.

    Args:
        title: Summary heading.
        details: Deployment URLs, refs, and status text.
    """
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as file:
            file.write(f"### {title}\n\n")
            file.write("\n".join(f"- {line}" for line in details))
            file.write("\n\n")


def _current_production_ref(alias_output: str, production_url: str) -> str:
    """Find the alias-list row currently pointing at the production domain.

    Args:
        alias_output: Safe text from the Vercel alias list command.
        production_url: Configured production origin.

    Returns:
        Matching alias row, or a clear initial-deployment marker.
    """
    hostname = production_url.removeprefix("https://").rstrip("/")
    for line in alias_output.splitlines():
        if hostname.lower() in line.lower():
            return line.strip()
    return "No previous production alias was listed."


def stage_deployment() -> None:
    """Build and create a production-target deployment without live aliases.

    Raises:
        RuntimeError: Vercel commands fail or return no staged deployment URL.
    """
    project_id = os.environ.get("VERCEL_PROJECT_ID", "")
    release_sha = os.environ.get("RELEASE_SHA", "")
    production_url = os.environ.get("VERCEL_PRODUCTION_URL", "")
    if not project_id or len(release_sha) != 40 or not production_url:
        raise RuntimeError("Vercel project, URL, or release SHA is missing.")
    _cli(["link", "--yes", "--project", project_id])
    _cli(["pull", "--yes", "--environment=production"])
    _cli(["build", "--prod"])
    subprocess.run(
        [sys.executable, "-m", "scripts.deployment.assert_release_current"],
        cwd=REPOSITORY_ROOT,
        check=True,
        timeout=30,
    )
    previous = _current_production_ref(
        _cli(["alias", "list", "--no-color"], timeout=120),
        production_url,
    )
    output = _cli(
        [
            "deploy",
            "--prebuilt",
            "--prod",
            "--skip-domain",
            "--yes",
            "--env",
            f"APP_RELEASE_SHA={release_sha}",
        ],
        timeout=900,
    )
    urls = URL_PATTERN.findall(output)
    if not urls:
        raise RuntimeError("Vercel did not return a staged deployment URL.")
    stage_url = urls[-1].rstrip(".,)")
    _write_output("stage_url", stage_url)
    _write_output("previous_deployment_ref", previous)
    _write_summary(
        "Vercel staged deployment",
        [
            f"Candidate: {stage_url}",
            f"Previous production alias: {previous}",
            f"Release: {release_sha}",
            "Candidate was staged without assigning production domains.",
        ],
    )
    print(f"Staged Vercel candidate: {stage_url}")


def promote_deployment() -> None:
    """Promote a smoke-tested staged deployment and record its production URL.

    Raises:
        RuntimeError: The candidate is absent or promotion fails.
    """
    candidate = os.environ.get("VERCEL_STAGE_URL", "")
    production_url = os.environ.get("VERCEL_PRODUCTION_URL", "")
    project_id = os.environ.get("VERCEL_PROJECT_ID", "")
    previous = os.environ.get(
        "VERCEL_PREVIOUS_DEPLOYMENT_REF",
        "No previous production alias was listed.",
    )
    if not candidate or not production_url or not project_id:
        raise RuntimeError("Vercel project and deployment URLs are required.")
    _cli(["link", "--yes", "--project", project_id])
    subprocess.run(
        [sys.executable, "-m", "scripts.deployment.assert_release_current"],
        cwd=REPOSITORY_ROOT,
        check=True,
        timeout=30,
    )
    _cli(["promote", candidate, "--yes"], timeout=300)
    _write_output("production_url", production_url)
    _write_summary(
        "Vercel promotion",
        [
            f"Promoted candidate: {candidate}",
            f"Production URL: {production_url}",
            f"Previous production alias: {previous}",
            f"Release: {os.environ['RELEASE_SHA']}",
        ],
    )
    print(f"Promoted Vercel candidate to {production_url}")


def main() -> int:
    """Dispatch the Vercel staging or promotion action.

    Returns:
        Zero only when the selected Vercel operation succeeds.
    """
    operation = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if operation == "stage":
            stage_deployment()
        elif operation == "promote":
            promote_deployment()
        else:
            print("Choose either 'stage' or 'promote'.")
            return 2
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
