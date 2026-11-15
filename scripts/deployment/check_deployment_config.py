"""Check deployment contracts without contacting cloud services.

The checks compare pinned tools, dedicated resource names, release metadata,
and workflow dependencies using only repository files.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts.deployment.cloudflare_config import (
    DATABASE_NAME,
    PLACEHOLDER_DATABASE_ID,
    WORKER_NAME,
    WORKER_ROOT,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/ci.yml"
WORKFLOW_DIRECTORY = REPOSITORY_ROOT / ".github/workflows"


def _needs_text(workflow: str, job_name: str) -> str:
    """Return the job block used for a small dependency-graph assertion.

    Args:
        workflow: Workflow YAML source.
        job_name: Job identifier at the two-space indentation level.

    Returns:
        The job block through the next peer job or end of file.
    """
    match = re.search(
        rf"(?ms)^  {re.escape(job_name)}:\n(.*?)(?=^  [a-zA-Z0-9_-]+:|\Z)",
        workflow,
    )
    return match.group(1) if match else ""


def configuration_errors() -> list[str]:
    """Collect inconsistent deployment names, pins, and workflow ordering.

    Returns:
        Human-readable errors; an empty list means the static contract agrees.
    """
    errors: list[str] = []
    package: dict[str, Any] = json.loads(
        (WORKER_ROOT / "package.json").read_text(encoding="utf-8")
    )
    lock = json.loads(
        (WORKER_ROOT / "package-lock.json").read_text(encoding="utf-8")
    )
    wrangler = json.loads(
        (WORKER_ROOT / "wrangler.jsonc").read_text(encoding="utf-8")
    )
    vercel = json.loads(
        (REPOSITORY_ROOT / "vercel.json").read_text(encoding="utf-8")
    )
    requirements = (
        REPOSITORY_ROOT / "apps/ui/requirements.txt"
    ).read_text(encoding="utf-8").splitlines()
    streamlit_startup = (
        REPOSITORY_ROOT / "scripts/deployment/check_streamlit_startup.py"
    ).read_text(encoding="utf-8")

    worker_pin = package.get("devDependencies", {}).get("wrangler")
    locked_pin = lock.get("packages", {}).get("node_modules/wrangler", {})
    if not worker_pin or worker_pin != locked_pin.get("version"):
        errors.append("Wrangler must be exactly pinned in both npm manifests.")
    if package.get("scripts", {}).get("migrate:local") is None:
        errors.append(
            "The Worker package must expose local D1 migration apply."
        )
    for command in (
        "test",
        "test:unit",
        "test:integration",
        "typecheck",
        "validate-config",
        "migrations:remote:list",
        "migrate:remote",
        "deploy",
    ):
        if command not in package.get("scripts", {}):
            errors.append(f"The Worker package is missing {command}.")
    if (
        wrangler.get("name") != WORKER_NAME
        or wrangler.get("vars", {}).get("APP_RELEASE_SHA") != "local"
        or wrangler["d1_databases"][0].get("database_name") != DATABASE_NAME
        or wrangler["d1_databases"][0].get("database_id")
        != PLACEHOLDER_DATABASE_ID
    ):
        errors.append(
            "Wrangler must keep the dedicated local placeholder config."
        )
    if vercel.get("git", {}).get("deploymentEnabled") is not False:
        errors.append("Vercel Git auto-deployments must be disabled.")
    if not requirements or any(
        "==" not in line or line.lstrip().startswith("#")
        for line in requirements
    ):
        errors.append(
            "Streamlit dependencies must be exact pinned requirements."
        )
    if 'if __name__ == "__main__":' not in streamlit_startup:
        errors.append("The Streamlit startup check must run when invoked.")

    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    workflow_files = {
        path.name for path in WORKFLOW_DIRECTORY.glob("*.yml")
    } | {path.name for path in WORKFLOW_DIRECTORY.glob("*.yaml")}
    if workflow_files != {"ci.yml"}:
        errors.append("All GitHub Actions jobs must live in ci.yml.")
    if "workflow_call:" in ci or "workflow_run:" in ci:
        errors.append("ci.yml must run as one consolidated workflow.")
    mandatory_jobs = {
        "lint",
        "format",
        "build",
        "tests",
        "docblocks",
        "comments",
        "line-length",
        "syntax",
        "typecheck",
        "dependency-audit",
        "npm-audit",
        "cloudflare-config",
        "cloudflare-migrations",
        "cloudflare-typecheck",
        "cloudflare-unit",
        "cloudflare-integration",
        "d1-api-integration",
        "docker-api-ui",
        "github-actions",
        "deployment-config",
        "streamlit-smoke",
    }
    gate = _needs_text(ci, "ci-gate")
    if "actions/checkout@" not in gate:
        errors.append("ci-gate must check out its result validator.")
    for job in mandatory_jobs:
        if not re.search(rf"(?m)^      - {re.escape(job)}$", gate):
            errors.append(f"ci-gate is missing mandatory job {job}.")

    sequence = (
        ("readiness", "ci-gate"),
        ("deploy-cloudflare", "readiness"),
        ("smoke-cloudflare", "deploy-cloudflare"),
        ("deploy-vercel", "smoke-cloudflare"),
        ("smoke-vercel", "deploy-vercel"),
        ("promote-vercel", "smoke-vercel"),
        ("promote-streamlit", "promote-vercel"),
        ("streamlit-readiness", "promote-streamlit"),
        ("post-deploy-cloudflare", "streamlit-readiness"),
        ("post-deploy-vercel", "streamlit-readiness"),
        ("post-deploy-streamlit", "streamlit-readiness"),
        ("post-deploy-end-to-end", "post-deploy-cloudflare"),
        ("post-deploy-smoke-result", "post-deploy-end-to-end"),
    )
    for job_name, required_dependency in sequence:
        block = _needs_text(ci, job_name)
        if not block or required_dependency not in block:
            errors.append(
                f"Workflow job {job_name} must depend on "
                f"{required_dependency}."
            )
    for required_job in (
        "deploy-cloudflare",
        "smoke-cloudflare",
        "deploy-vercel",
        "smoke-vercel",
        "promote-vercel",
        "promote-streamlit",
        "streamlit-readiness",
        "post-deploy-cloudflare",
        "post-deploy-vercel",
        "post-deploy-streamlit",
        "post-deploy-end-to-end",
        "post-deploy-smoke-result",
        "deployment-result",
    ):
        if not _needs_text(ci, required_job):
            errors.append(f"ci.yml is missing deployment job {required_job}.")
    for protected_smoke_job in (
        "post-deploy-cloudflare",
        "post-deploy-vercel",
        "post-deploy-end-to-end",
    ):
        block = _needs_text(ci, protected_smoke_job)
        if not re.search(r"(?m)^    environment: production$", block):
            errors.append(
                "Smoke job must read credentials from production "
                f"environment: {protected_smoke_job}."
            )
    readiness = _needs_text(ci, "readiness")
    if "needs.ci-gate.result == 'success'" not in readiness:
        errors.append("Deployment readiness must require a successful CI gate.")
    if "github.ref == 'refs/heads/main'" not in readiness:
        errors.append("Automatic deployment must be restricted to main.")
    if "github.event_name == 'workflow_dispatch'" not in readiness:
        errors.append("Manual deployments must use the consolidated workflow.")
    worker_source = (WORKER_ROOT / "src/index.ts").read_text(
        encoding="utf-8"
    )
    cloudflare_smoke = (
        REPOSITORY_ROOT / "scripts/deployment/smoke_cloudflare.py"
    ).read_text(encoding="utf-8")
    if 'url.pathname === "/health"' not in worker_source:
        errors.append("The Worker must expose a public health endpoint.")
    if "health.get(\"release_sha\") != release_sha" not in cloudflare_smoke:
        errors.append("Cloudflare smoke must verify the Worker release SHA.")
    for action_ref in re.findall(
        r"(?m)^\s+uses:\s+([^\s]+)",
        ci,
    ):
        if action_ref.startswith("./"):
            continue
        if not re.search(r"@[0-9a-f]{40}$", action_ref):
            errors.append(
                f"Workflow action is not pinned to a SHA: {action_ref}."
            )
    return errors


def main() -> int:
    """Run static deployment configuration consistency checks.

    Returns:
        Zero only when every required configuration is consistent.
    """
    errors = configuration_errors()
    if errors:
        for error in errors:
            print(error)
        return 1
    print("Deployment configuration and workflow dependencies are consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
