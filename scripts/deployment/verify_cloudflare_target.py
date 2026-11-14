"""Verify the Cloudflare D1 database name and ID before remote changes.

The API token is used only for the identity query and is never written to
stdout or included in reported error details.
"""

import sys

from scripts.deployment.cloudflare_config import verify_cloudflare_database


def main() -> int:
    """Check the dedicated D1 database using the configured API token.

    Returns:
        Zero only when Cloudflare confirms the exact database identity.
    """
    try:
        verify_cloudflare_database()
    except (RuntimeError, ValueError) as exc:
        print(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
