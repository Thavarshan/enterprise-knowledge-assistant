"""Run guarded, pinned Wrangler operations for the D1 gateway.

Remote calls use the repository-local Wrangler package and require both CI
authorization and an exact Cloudflare database identity check.
"""

import os
import subprocess
import sys
from pathlib import Path

from scripts.deployment.cloudflare_config import (
    WORKER_ROOT,
    render_wrangler_config,
    require_gated_cloud_deployment,
    verify_cloudflare_database,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def assert_release_current() -> None:
    """Stop before a remote mutation when origin/main has moved.

    Raises:
        RuntimeError: Release metadata is absent or the commit is stale.
    """
    release_sha = os.environ.get("RELEASE_SHA", "")
    if len(release_sha) != 40:
        raise RuntimeError("A full CI-approved release SHA is required.")
    subprocess.run(
        [sys.executable, "scripts/deployment/assert_release_current.py"],
        cwd=REPOSITORY_ROOT,
        check=True,
        timeout=30,
    )


def run_wrangler(*arguments: str) -> None:
    """Invoke the repository-locked Wrangler package without shell parsing.

    Args:
        arguments: Wrangler arguments after the package executable.

    Raises:
        subprocess.CalledProcessError: Wrangler returned a non-zero status.
    """
    subprocess.run(
        ["npm", "exec", "--", "wrangler", *arguments],
        cwd=WORKER_ROOT,
        check=True,
        timeout=600,
    )


def apply_remote_migrations() -> None:
    """Inspect and apply approved additive migrations to the dedicated D1.

    Raises:
        RuntimeError: Deployment authorization or migration safety fails.
        subprocess.CalledProcessError: Wrangler migration execution fails.
    """
    require_gated_cloud_deployment()
    render_wrangler_config()
    verify_cloudflare_database()
    subprocess.run(
        [
            sys.executable,
            "scripts/deployment/validate_d1_migrations.py",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        timeout=30,
    )
    config = "wrangler.deploy.jsonc"
    run_wrangler(
        "d1",
        "migrations",
        "list",
        "eka-assessment-d1",
        "--remote",
        "--config",
        config,
    )
    assert_release_current()
    run_wrangler(
        "d1",
        "migrations",
        "apply",
        "eka-assessment-d1",
        "--remote",
        "--config",
        config,
    )


def deploy_worker() -> None:
    """Deploy the Worker with its service secret from a temporary file.

    Raises:
        RuntimeError: Deployment authorization or required secrets are absent.
        subprocess.CalledProcessError: Wrangler deployment fails.
    """
    import json
    import tempfile

    require_gated_cloud_deployment()
    secret = os.environ.get("D1_SERVICE_TOKEN", "")
    if len(secret) < 32:
        raise RuntimeError("D1_SERVICE_TOKEN must contain at least 32 chars.")
    render_wrangler_config()
    verify_cloudflare_database()
    assert_release_current()

    descriptor, secret_path = tempfile.mkstemp(
        prefix="eka-worker-secret-", suffix=".json"
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({"D1_SERVICE_TOKEN": secret}, output)
        run_wrangler(
            "deploy",
            "--config",
            "wrangler.deploy.jsonc",
            "--strict",
            "--secrets-file",
            secret_path,
            "--message",
            f"CI release {os.environ['RELEASE_SHA'][:12]}",
            "--tag",
            os.environ["RELEASE_SHA"],
        )
    finally:
        try:
            os.unlink(secret_path)
        except FileNotFoundError:
            pass
