"""Fail before remote changes when required deployment settings are absent.

The preflight prints setting names only and validates public origins without
reading or displaying any configured secret value.
"""

import os
import sys

from scripts.deployment.smoke_http import SmokeCheckError, https_origin

REQUIRED_VALUES = (
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_D1_DATABASE_ID",
    "CLOUDFLARE_API_TOKEN",
    "D1_SERVICE_TOKEN",
    "CLOUDFLARE_WORKER_URL",
    "VERCEL_TOKEN",
    "VERCEL_ORG_ID",
    "VERCEL_PROJECT_ID",
    "VERCEL_PRODUCTION_URL",
    "VERCEL_AUTOMATION_BYPASS_SECRET",
    "STREAMLIT_URL",
    "STREAMLIT_BRANCH",
    "SMOKE_ANALYST_PASSWORD",
    "SMOKE_VIEWER_PASSWORD",
)


def main() -> int:
    """Validate all named vars and secrets without printing their values.

    Returns:
        Zero when the initial production configuration is complete.
    """
    missing = [name for name in REQUIRED_VALUES if not os.environ.get(name)]
    if missing:
        print("Deployment configuration is missing: " + ", ".join(missing))
        return 1
    if len(os.environ["D1_SERVICE_TOKEN"]) < 32:
        print("D1_SERVICE_TOKEN must contain at least 32 characters.")
        return 1
    for name in (
        "CLOUDFLARE_WORKER_URL",
        "VERCEL_PRODUCTION_URL",
        "STREAMLIT_URL",
    ):
        try:
            https_origin(os.environ[name], name)
        except SmokeCheckError as exc:
            print(str(exc))
            return 1
    if os.environ["STREAMLIT_BRANCH"] != "deploy/streamlit":
        print("STREAMLIT_BRANCH must equal deploy/streamlit.")
        return 1
    print("Required deployment variables and secret names are configured.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
