"""Deploy the D1 Worker through the approved CI workflow only.

The deployment runner places the service token in a short-lived restricted
file and removes that file after Wrangler exits.
"""

import sys

from scripts.deployment.cloudflare_runner import deploy_worker


def main() -> int:
    """Run Wrangler with a short-lived, permission-restricted secrets file.

    Returns:
        Zero only when the Worker deploy command succeeds.
    """
    try:
        deploy_worker()
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc))
        return 1
    except Exception as exc:
        if hasattr(exc, "returncode"):
            print(f"Wrangler deployment failed: exit {exc.returncode}.")
            return 1
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
