"""Inspect the migration state of the dedicated remote D1 database.

The read-only inspection still requires the protected CI context and verifies
the exact database before asking Wrangler for its migration history.
"""

import sys

from scripts.deployment.cloudflare_config import (
    DATABASE_NAME,
    DEPLOY_CONFIG,
    render_wrangler_config,
    require_gated_cloud_deployment,
    verify_cloudflare_database,
)
from scripts.deployment.cloudflare_runner import (
    assert_release_current,
    run_wrangler,
)


def main() -> int:
    """Verify deployment authorization and print remote migration status.

    Returns:
        Zero only when the dedicated target's migration list was read.
    """
    try:
        require_gated_cloud_deployment()
        render_wrangler_config()
        verify_cloudflare_database()
        assert_release_current()
        run_wrangler(
            "d1",
            "migrations",
            "list",
            DATABASE_NAME,
            "--remote",
            "--config",
            DEPLOY_CONFIG.name,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc))
        return 1
    except Exception as exc:
        if hasattr(exc, "returncode"):
            print(f"Wrangler migration inspection failed: {exc.returncode}.")
            return 1
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
