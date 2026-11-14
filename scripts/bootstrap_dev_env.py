"""Create ignored, one-time local demo credentials in the repository .env."""

import json
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
EXAMPLE_PATH = ROOT / ".env.example"


def main() -> None:
    contents = (
        ENV_PATH.read_text(encoding="utf-8")
        if ENV_PATH.exists()
        else EXAMPLE_PATH.read_text(encoding="utf-8")
    )
    existing_value = next(
        (
            line.partition("=")[2].strip().strip("'\"")
            for line in contents.splitlines()
            if line.startswith("DEV_USERS_JSON=")
        ),
        "",
    )
    if existing_value:
        ENV_PATH.write_text(contents.rstrip() + "\n", encoding="utf-8")
        print("Using development accounts already configured in .env.")
        return

    accounts = {
        username: {"password": secrets.token_urlsafe(18), "role": role}
        for username, role in (
            ("viewer", "viewer"),
            ("analyst", "analyst"),
            ("admin", "administrator"),
        )
    }
    encoded = json.dumps(accounts, separators=(",", ":"))
    ENV_PATH.write_text(
        contents.rstrip() + f"\nDEV_USERS_JSON='{encoded}'\n",
        encoding="utf-8",
    )
    print(
        "Generated local-only demo credentials. "
        "Store these outside the repository:"
    )
    for username, account in accounts.items():
        print(f"  {username}: {account['password']}")
    print(
        "The credentials are saved in ignored .env and are not logged "
        "by the application."
    )


if __name__ == "__main__":
    main()
