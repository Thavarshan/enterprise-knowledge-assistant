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
API_WRANGLER_CONFIG = REPOSITORY_ROOT / "wrangler.jsonc"
API_ENTRYPOINT = REPOSITORY_ROOT / "src/worker_entry.py"
VERCEL_CONFIG = REPOSITORY_ROOT / "vercel.json"
VERCEL_INSTALL_SCRIPT = REPOSITORY_ROOT / "vercel-install.sh"
VERCEL_IGNORE_FILE = REPOSITORY_ROOT / ".vercelignore"
PYTHON_VERSION_FILE = REPOSITORY_ROOT / ".python-version"
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
    api_worker = json.loads(API_WRANGLER_CONFIG.read_text(encoding="utf-8"))
    vercel = json.loads(VERCEL_CONFIG.read_text(encoding="utf-8"))
    vercel_install = VERCEL_INSTALL_SCRIPT.read_text(encoding="utf-8")
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
    if (
        api_worker.get("name") != "viridian"
        or api_worker.get("compatibility_flags") != ["python_workers"]
        or api_worker.get("vars", {}).get("MOCK_MODE") != "true"
        or api_worker.get("vars", {}).get("LLM_PROVIDER") != "mock"
        or api_worker.get("vars", {}).get("LANGSMITH_TRACING") != "false"
        or api_worker.get("assets", {}).get("binding") != "ASSETS"
        or "/api/*"
        not in api_worker.get("assets", {}).get("run_worker_first", [])
    ):
        errors.append(
            "Viridian must keep its free Python Worker, mock providers, "
            "and static asset routing."
        )
    if (
        vercel.get("installCommand") != "bash vercel-install.sh"
        or "uv sync --frozen --no-default-groups" not in vercel_install
        or "--python 3.12" not in vercel_install
        or PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip() != "3.12"
        or "--extra agents" not in vercel_install
        or "--extra providers" not in vercel_install
        or vercel.get("functions", {}).get("app.py", {}).get("maxDuration", 0)
        < 60
        or vercel.get("git", {}).get("deploymentEnabled") is not False
    ):
        errors.append(
            "Vercel must build the full Viridian API and disable "
            "ungated Git deploys."
        )
    if VERCEL_IGNORE_FILE.exists():
        errors.append(
            "Do not add .vercelignore; prebuilt uploads need traced files."
        )
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    if "VERCEL_TOKEN" not in ci or "vercel deploy --prebuilt --prod" not in ci:
        errors.append("The production workflow must deploy the Vercel API.")
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
        "docker-compose-api",
        "github-actions",
        "deployment-config",
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
        ("deploy-vercel-api", "smoke-cloudflare"),
        ("smoke-vercel-api", "deploy-vercel-api"),
        ("deployment-result", "smoke-vercel-api"),
    )
    for job_name, required_dependency in sequence:
        block = _needs_text(ci, job_name)
        if not block or required_dependency not in block:
            errors.append(
                f"Workflow job {job_name} must depend on {required_dependency}."
            )
    for required_job in (
        "deploy-cloudflare",
        "smoke-cloudflare",
        "deploy-vercel-api",
        "smoke-vercel-api",
        "deployment-result",
    ):
        if not _needs_text(ci, required_job):
            errors.append(f"ci.yml is missing deployment job {required_job}.")
    for protected_smoke_job in (
        "smoke-cloudflare",
        "smoke-vercel-api",
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
    worker_source = (WORKER_ROOT / "src/index.ts").read_text(encoding="utf-8")
    if not API_ENTRYPOINT.exists():
        errors.append("The Viridian Python Worker entrypoint is missing.")
    cloudflare_smoke = (
        REPOSITORY_ROOT / "scripts/deployment/smoke_cloudflare.py"
    ).read_text(encoding="utf-8")
    if 'url.pathname === "/health"' not in worker_source:
        errors.append("The Worker must expose a public health endpoint.")
    if 'health.get("release_sha") != release_sha' not in cloudflare_smoke:
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
