"""Poll Community Cloud for the exact source release with bounded retries.

Streamlit exposes no deployment status API in this integration, so readiness
uses the visible application SHA and a fixed browser-probe deadline.
"""

import sys
import time

from scripts.deployment.smoke_http import SmokeCheckError, write_summary
from scripts.deployment.smoke_streamlit import run_smoke

ATTEMPTS = 15
RETRY_SECONDS = 20


def main() -> int:
    """Retry browser readiness a bounded number of times after branch update.

    Returns:
        Zero only when the expected release is visible in Community Cloud.
    """
    last_error = "no attempt completed"
    for attempt in range(1, ATTEMPTS + 1):
        try:
            run_smoke()
            print(f"Streamlit became ready on attempt {attempt}.")
            return 0
        except SmokeCheckError as exc:
            last_error = str(exc)
            if attempt < ATTEMPTS:
                print(
                    f"Streamlit readiness attempt {attempt} is still pending."
                )
                time.sleep(RETRY_SECONDS)
    message = (
        f"Expected release was not visible after {ATTEMPTS} attempts: "
        f"{last_error}"
    )
    write_summary("Streamlit readiness FAILED", [message])
    print(message)
    return 1


if __name__ == "__main__":
    sys.exit(main())
