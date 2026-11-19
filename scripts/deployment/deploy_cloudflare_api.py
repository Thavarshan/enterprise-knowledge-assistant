"""Deploy the Viridian Python API and static frontend through Wrangler."""

import os
import subprocess
import sys

from scripts.deployment.cloudflare_api_config import (
    WORKER_ROOT,
    render_wrangler_config,
)
from scripts.deployment.cloudflare_config import (
    require_gated_cloud_deployment,
    verify_cloudflare_database,
)
from scripts.deployment.cloudflare_runner import assert_release_current
from scripts.deployment.generate_cloudflare_fixtures import (
    prepare_worker_fixtures,
    remove_worker_fixtures,
)
from scripts.deployment.render_cloudflare_api_secrets import render_secrets


def deploy_api_worker() -> None:
    """Deploy the release after confirming CI authorization and D1 identity."""
    require_gated_cloud_deployment()
    release_sha = os.environ.get("RELEASE_SHA", "")
    if len(release_sha) != 40:
        raise RuntimeError("A full CI-approved release SHA is required.")
    config_path = render_wrangler_config()
    secrets_path = render_secrets()
    try:
        prepare_worker_fixtures()
        verify_cloudflare_database()
        assert_release_current()
        subprocess.run(
            [
                "uv",
                "run",
                "pywrangler",
                "deploy",
                "--config",
                config_path.name,
                "--strict",
                "--secrets-file",
                str(secrets_path),
                "--message",
                f"CI release {release_sha[:12]}",
                "--tag",
                release_sha,
            ],
            cwd=WORKER_ROOT,
            check=True,
            timeout=900,
        )
    finally:
        try:
            secrets_path.unlink()
        except FileNotFoundError:
            pass
        remove_worker_fixtures()


def main() -> int:
    """Deploy the API and frontend without displaying credential values."""
    try:
        deploy_api_worker()
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Viridian API deployment failed: {exc}")
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"Python Worker deployment failed with exit {exc.returncode}.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
