"""Regression coverage for Streamlit's app-directory module search path."""

import subprocess
import sys
from pathlib import Path


def test_ui_api_client_imports_when_running_from_the_streamlit_directory() -> None:
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
