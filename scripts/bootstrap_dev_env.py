"""Create local development users and configure the `.env` file path.

The script generates random passwords only when the configured JSON file is
missing, writes the file with restrictive permissions, and prints the
one-time passwords to the invoking developer. Existing inline JSON and
existing files are preserved.
"""

import json
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
EXAMPLE_PATH = ROOT / ".env.example"
DEFAULT_USERS_PATH = Path("data/users/default.json")


def _configured_value(contents: str) -> str:
    """Read the current DEV_USERS_JSON value from dotenv text.

    Args:
        contents: Complete local environment-file contents.

    Returns:
        The first configured value with surrounding quotes removed, or an
        empty string when the setting is absent.
    """
    return next(
        (
            line.partition("=")[2].strip().strip("'\"")
            for line in contents.splitlines()
            if line.startswith("DEV_USERS_JSON=")
        ),
        "",
    )


def _set_configured_path(contents: str, users_path: str) -> str:
    """Replace duplicate user settings with one configured path.

    Args:
        contents: Existing environment-file text to preserve.
        users_path: Relative or absolute account-file value to write.

    Returns:
        Updated dotenv text ending in one newline.
    """
    lines = contents.splitlines()
    updated: list[str] = []
    added = False
    for line in lines:
        if line.startswith("DEV_USERS_JSON="):
            if not added:
                updated.append(f"DEV_USERS_JSON={users_path}")
                added = True
            continue
        updated.append(line)
    if not added:
        updated.append(f"DEV_USERS_JSON={users_path}")
    return "\n".join(updated).rstrip() + "\n"


def main() -> None:
    """Ensure local development accounts exist and update .env.

    Existing inline JSON and existing account files are retained. When no
    file exists, the script generates random passwords, creates the parent
    directory with restrictive permissions, creates the file exclusively
    with mode 0600, and prints the one-time credentials to the terminal.

    Side Effects:
        Reads .env or .env.example; writes .env and possibly a local account
        JSON file. The generated credential file is expected to be ignored
        by Git.
    """
    contents = (
        ENV_PATH.read_text(encoding="utf-8")
        if ENV_PATH.exists()
        else EXAMPLE_PATH.read_text(encoding="utf-8")
    )
    existing_value = _configured_value(contents)
    if existing_value.lstrip().startswith("{"):
        ENV_PATH.write_text(contents.rstrip() + "\n", encoding="utf-8")
        print("Using development accounts already configured in .env.")
        return

    configured_path = existing_value or DEFAULT_USERS_PATH.as_posix()
    users_path = Path(configured_path).expanduser()
    if not users_path.is_absolute():
        users_path = ROOT / users_path
    contents = _set_configured_path(contents, configured_path)

    if users_path.is_file():
        ENV_PATH.write_text(contents, encoding="utf-8")
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
    users_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(users_path.parent, 0o700)
    descriptor = os.open(
        users_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as users_file:
        json.dump(accounts, users_file, indent=2)
        users_file.write("\n")
    ENV_PATH.write_text(contents, encoding="utf-8")
    print(
        "Generated local-only demo credentials. "
        "Store these outside the repository:"
    )
    for username, account in accounts.items():
        print(f"  {username}: {account['password']}")
    print(
        "The credentials are saved in an ignored JSON file and are not "
        "logged by the application."
    )


if __name__ == "__main__":
    main()
