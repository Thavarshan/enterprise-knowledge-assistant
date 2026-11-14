"""Resolve a non-sensitive source revision for the Streamlit interface.

Community Cloud follows a Git branch rather than a deployment API. The UI
uses checkout metadata to expose the revision actually loaded by its process.
"""

import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

_RELEASE_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def resolve_release_sha(
    environment: Mapping[str, str],
    repository_root: Path,
) -> str:
    """Return a validated release SHA from runtime or Git metadata.

    Args:
        environment: Runtime variables that may include the expected release.
        repository_root: Root directory of the checked out repository.

    Returns:
        A lowercase 40-character SHA, or ``unavailable`` if unknown.
    """
    configured = environment.get("APP_RELEASE_SHA", "").lower()
    if _RELEASE_SHA_PATTERN.fullmatch(configured):
        return configured
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            capture_output=True,
            check=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    release_sha = result.stdout.strip().lower()
    return (
        release_sha
        if _RELEASE_SHA_PATTERN.fullmatch(release_sha)
        else "unavailable"
    )
