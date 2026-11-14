"""Verify Community Cloud serves the expected Streamlit source revision.

The browser check reads the public release label and does not inspect platform
internals or access application credentials.
"""

import os
import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from scripts.deployment.smoke_http import (
    SmokeCheckError,
    https_origin,
    write_summary,
)


def run_smoke() -> None:
    """Load the browser app and require its visible release SHA to match.

    Raises:
        SmokeCheckError: The app is unreachable or reports the wrong revision.
    """
    origin = https_origin(
        os.environ.get("STREAMLIT_URL", ""),
        "STREAMLIT_URL",
    )
    expected_sha = os.environ.get("RELEASE_SHA", "").lower()
    if len(expected_sha) != 40:
        raise SmokeCheckError("A full expected release SHA is required.")
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            response = page.goto(
                origin,
                wait_until="domcontentloaded",
                timeout=25_000,
            )
            if response is None or response.status >= 400:
                raise SmokeCheckError("Streamlit did not return a page.")
            page.get_by_text(
                "Enterprise Knowledge Assistant",
                exact=True,
            ).first.wait_for(timeout=10_000)
            page.get_by_text(
                f"Application release: {expected_sha}",
                exact=True,
            ).wait_for(timeout=10_000)
            browser.close()
    except PlaywrightTimeoutError as exc:
        raise SmokeCheckError(
            "Streamlit did not display the expected application revision."
        ) from exc
    write_summary(
        "Streamlit Community Cloud",
        [f"URL: {origin}", f"Visible application release: {expected_sha}"],
    )
    print("Streamlit page and visible release SHA smoke passed.")


def main() -> int:
    """Run the Streamlit browser readiness check.

    Returns:
        Zero only when the expected application revision is visible.
    """
    try:
        run_smoke()
    except SmokeCheckError as exc:
        write_summary("Streamlit Community Cloud FAILED", [str(exc)])
        print(f"Streamlit smoke failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
