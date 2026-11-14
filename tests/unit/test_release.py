"""Verify the Streamlit release label uses safe source metadata.

The UI must reject unvalidated runtime values and fall back to Git metadata.
"""

from pathlib import Path

from apps.ui.services.release import resolve_release_sha


def test_release_sha_uses_validated_runtime_value() -> None:
    """Prefer an exact deployment SHA supplied by the environment.

    Release values are normalized and validated before they are shown in the UI.
    """
    expected = "A" * 40

    assert resolve_release_sha(
        {"APP_RELEASE_SHA": expected},
        Path("/missing/repository"),
    ) == expected.lower()


def test_release_sha_reports_unavailable_without_git_metadata(
    tmp_path: Path,
) -> None:
    """Avoid presenting untrusted release text as a source revision.

    Invalid input stays unavailable when the checkout has no Git metadata.
    """
    assert resolve_release_sha(
        {"APP_RELEASE_SHA": "release-latest"},
        tmp_path,
    ) == "unavailable"
