"""Protect the UI client's import behavior from its app directory.

The test launches a short child Python process with the Streamlit directory
as its working directory, matching the package-resolution context used by
the UI command.
"""

import subprocess
import sys
from pathlib import Path


def test_ui_api_client_imports_when_running_from_the_streamlit_directory() -> (
    None
):
    """Verify the UI package imports from its launch working directory.

    A child interpreter mirrors the package-resolution context used by
    Streamlit without starting the UI server.
    """
    repository_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from apps.ui.services.api_client import AssistantApiClient",
        ],
        cwd=repository_root / "apps" / "ui",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
