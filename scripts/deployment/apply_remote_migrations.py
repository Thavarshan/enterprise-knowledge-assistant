"""Apply forward-only D1 changes after protected CI approval.

The command delegates to guarded Wrangler operations and never rolls back
schema changes automatically.
"""

import sys

from scripts.deployment.cloudflare_runner import apply_remote_migrations


def main() -> int:
    """Run the guarded remote migration operation.

    Returns:
        Zero only when the dedicated D1 migration command succeeds.
    """
    try:
        apply_remote_migrations()
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc))
        return 1
    except Exception as exc:
        if hasattr(exc, "returncode"):
            print(f"Wrangler migration command failed: exit {exc.returncode}.")
            return 1
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
