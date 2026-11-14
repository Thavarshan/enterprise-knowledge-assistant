"""Fail the aggregate CI gate when any required job is not successful.

GitHub supplies direct dependency results as JSON; this helper requires every
listed result to be successful, including when a job was cancelled or skipped.
"""

import json
import os
import sys
from typing import Any

from scripts.deployment.policy import failed_ci_jobs


def main() -> int:
    """Validate the JSON-encoded result of every mandatory CI dependency.

    Returns:
        Zero only when each required job completed successfully.
    """
    try:
        jobs: dict[str, Any] = json.loads(os.environ["CI_NEEDS_JSON"])
    except (KeyError, json.JSONDecodeError):
        print("The required CI job results were not available.")
        return 1
    if not jobs:
        print("The CI workflow returned no required job results.")
        return 1
    results = {
        name: (
            str(details.get("result", "missing"))
            if isinstance(details, dict)
            else "missing"
        )
        for name, details in jobs.items()
    }
    failures = failed_ci_jobs(results)
    if failures:
        summary = ", ".join(
            f"{name}={result}" for name, result in sorted(failures.items())
        )
        print(f"CI gate blocked by required job results: {summary}")
        return 1
    print(f"CI gate passed for {len(jobs)} required jobs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
