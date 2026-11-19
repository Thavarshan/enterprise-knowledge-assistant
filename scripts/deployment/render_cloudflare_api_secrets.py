"""Write Worker secrets to a private one-shot Wrangler input file.

The generated file is ignored by Git and deleted after the release command.
"""

import json
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SECRETS_PATH = (
    REPOSITORY_ROOT / "infra/cloudflare/viridian-api" / ".secrets.json"
)


def render_secrets() -> Path:
    """Serialize only required secrets and synthetic demo accounts.

    Raises:
        ValueError: A required secret is absent or malformed.
    """
    values = {
        name: os.environ.get(name, "")
        for name in (
            "AUTH_SIGNING_SECRET",
            "D1_SERVICE_TOKEN",
            "SMOKE_ANALYST_PASSWORD",
            "SMOKE_VIEWER_PASSWORD",
            "SMOKE_ADMIN_PASSWORD",
        )
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError("Missing required secrets: " + ", ".join(missing))
    if len(values["AUTH_SIGNING_SECRET"]) < 32:
        raise ValueError("AUTH_SIGNING_SECRET must contain at least 32 chars.")
    if len(values["D1_SERVICE_TOKEN"]) < 32:
        raise ValueError("D1_SERVICE_TOKEN must contain at least 32 chars.")

    users = {
        "viewer": {
            "password": values["SMOKE_VIEWER_PASSWORD"],
            "role": "viewer",
        },
        "analyst": {
            "password": values["SMOKE_ANALYST_PASSWORD"],
            "role": "analyst",
        },
        "admin": {
            "password": values["SMOKE_ADMIN_PASSWORD"],
            "role": "administrator",
        },
    }
    payload = {
        "AUTH_SIGNING_SECRET": values["AUTH_SIGNING_SECRET"],
        "D1_SERVICE_TOKEN": values["D1_SERVICE_TOKEN"],
        "DEV_USERS_JSON": json.dumps(users, separators=(",", ":")),
    }
    SECRETS_PATH.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    SECRETS_PATH.chmod(0o600)
    return SECRETS_PATH


def main() -> int:
    """Write secrets without displaying their values.

    Returns:
        Zero when secret input is prepared, otherwise one.
    """
    try:
        path = render_secrets()
    except (OSError, ValueError) as exc:
        print(f"Cloudflare secret preparation failed: {exc}")
        return 1
    print(f"Prepared private Cloudflare secret input: {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
