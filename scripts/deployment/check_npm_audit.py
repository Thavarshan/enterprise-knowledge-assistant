"""Run the Worker npm audit with one exact, unpatched advisory exception.

The allowed picomatch advisory currently has no patched release. Its affected
packages must remain development-only, and any other high or critical
advisory fails this check.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ADVISORY_URL = "https://github.com/advisories/GHSA-fc5q-39xc-vjpf"
ALLOWED_PACKAGES = frozenset(
    {
        "@cloudflare/vitest-plugin",
        "fdir",
        "picomatch",
        "tinyglobby",
        "vite",
        "vitest",
    }
)


def _load_audit() -> dict[str, Any]:
    """Run npm audit and return its JSON report.

    Returns:
        Parsed npm audit report.

    Raises:
        RuntimeError: If npm fails to produce a usable audit report.
    """
    try:
        result = subprocess.run(
            ["npm", "audit", "--audit-level=high", "--json"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError("Could not start npm audit.") from exc

    if result.returncode not in {0, 1}:
        raise RuntimeError("npm audit could not complete successfully.")

    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("npm audit returned invalid JSON.") from exc

    if (
        not isinstance(report, dict)
        or report.get("error")
        or not isinstance(report.get("auditReportVersion"), int)
        or not isinstance(report.get("metadata"), dict)
    ):
        raise RuntimeError("npm audit returned an error response.")
    return report


def _lockfile_marks_dev_only(package_names: set[str]) -> bool:
    """Confirm every audited package is development-only in the lockfile.

    Args:
        package_names: Vulnerable package names reported by npm audit.

    Returns:
        Whether all package instances are marked development-only.
    """
    try:
        lockfile = json.loads(Path("package-lock.json").read_text())
    except (OSError, json.JSONDecodeError):
        return False

    packages = lockfile.get("packages", {})
    for name in package_names:
        suffix = f"node_modules/{name}"
        matches = [
            package
            for path, package in packages.items()
            if path == suffix or path.endswith(f"/{suffix}")
        ]
        if not matches or any(item.get("dev") is not True for item in matches):
            return False
    return True


def _check_report(report: dict[str, Any]) -> list[str]:
    """Validate the audit report against the single advisory exception.

    Args:
        report: Parsed npm audit report.

    Returns:
        High or critical vulnerable package names.

    Raises:
        RuntimeError: If a finding falls outside the narrow exception.
    """
    vulnerabilities = report.get("vulnerabilities", {})
    if not isinstance(vulnerabilities, dict):
        raise RuntimeError("npm audit returned an invalid vulnerability list.")
    if any(not isinstance(item, dict) for item in vulnerabilities.values()):
        raise RuntimeError("npm audit returned an invalid vulnerability entry.")

    severe = {
        name: item
        for name, item in vulnerabilities.items()
        if item.get("severity") in {"high", "critical"}
    }
    if not severe:
        return []

    if not set(severe).issubset(ALLOWED_PACKAGES):
        raise RuntimeError("Unexpected high or critical npm advisory found.")

    advisory_urls: set[str] = set()
    for package_name, item in severe.items():
        via = item.get("via", [])
        if not isinstance(via, list) or not via:
            raise RuntimeError("npm audit returned an invalid advisory path.")
        for source in via:
            if isinstance(source, str):
                if source not in ALLOWED_PACKAGES:
                    raise RuntimeError(
                        "Unexpected npm advisory dependency path."
                    )
            elif isinstance(source, dict):
                url = source.get("url")
                if url != ADVISORY_URL:
                    raise RuntimeError(
                        "Unexpected high or critical npm advisory."
                    )
                advisory_urls.add(url)
            else:
                raise RuntimeError("npm audit returned an invalid advisory.")

        if package_name == "picomatch" and not any(
            isinstance(source, dict) and source.get("url") == ADVISORY_URL
            for source in via
        ):
            raise RuntimeError("The expected picomatch advisory was not found.")

    if advisory_urls != {ADVISORY_URL}:
        raise RuntimeError("The audit findings do not match the exception.")
    if not _lockfile_marks_dev_only(set(severe)):
        raise RuntimeError("An affected package is not development-only.")

    return sorted(severe)


def main() -> int:
    """Run the npm dependency audit and report its result.

    Returns:
        Process exit status compatible with a CI check.
    """
    try:
        affected_packages = _check_report(_load_audit())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if affected_packages:
        names = ", ".join(affected_packages)
        warning = (
            "Only the unpatched picomatch GHSA-fc5q-39xc-vjpf remains in "
            f"development-only packages: {names}."
        )
        print(f"::warning title=Known npm advisory::{warning}")
        print(warning)
    else:
        print("No high or critical npm advisories found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
