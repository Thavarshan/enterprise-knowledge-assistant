"""Stop a deployment stage when a newer commit has reached main.

The check reads the public Git remote and does not need cloud credentials or
write access to the repository.
"""

import os
import subprocess
import sys

from scripts.deployment.policy import release_is_current


def main() -> int:
    """Compare the approved SHA with the current remote main tip.

    Returns:
        Zero when the approved SHA remains current, otherwise one.
    """
    release_sha = os.environ.get("RELEASE_SHA", "")
    result = subprocess.run(
        ["git", "ls-remote", "origin", "refs/heads/main"],
        capture_output=True,
        check=False,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        print("Could not verify the current main branch tip.")
        return 1
    main_sha = result.stdout.split(maxsplit=1)[0]
    if not release_is_current(release_sha, main_sha):
        print("Deployment stopped because this release is stale.")
        return 1
    print("The approved release is still the current main commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
