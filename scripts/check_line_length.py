"""Check first-party source, configuration, and documentation line widths.

Generated dependency locks and the assessment source documents are excluded.
Long standalone Markdown URLs are allowed because they cannot be reflowed.
"""

from __future__ import annotations

import re
from pathlib import Path

MAX_LINE_LENGTH = 80
CHECKED_SUFFIXES = {
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
    ".jsonc",
}
CHECKED_NAMES = {
    ".dockerignore",
    ".dev.vars.example",
    ".env.cloud-sim.example",
    ".env.example",
    ".gitignore",
    "Dockerfile",
    "Makefile",
    "secrets.toml.example",
}
EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".venv-workers",
    "__pycache__",
    "build",
    "data",
    "dist",
    "node_modules",
    "python_modules",
    ".vercel",
}
EXCLUDED_FILES = {
    "docs/assignment.md",
    "docs/plan.md",
    "infra/cloudflare/d1-gateway/package-lock.json",
    "pylock.toml",
    ".streamlit/secrets.toml",
    "uv.lock",
}
MARKDOWN_URL = re.compile(r"^\[[^\]]+\]:\s+https?://\S+$")


def _is_checked_file(path: Path, root: Path) -> bool:
    """Return whether a repository file is in the line-width check.

    Args:
        path: Candidate file discovered below the repository root.
        root: Repository root used to build a stable relative path.
    """
    relative_path = path.relative_to(root).as_posix()
    if relative_path in EXCLUDED_FILES:
        return False
    if EXCLUDED_PARTS.intersection(path.parts):
        return False
    return path.suffix in CHECKED_SUFFIXES or path.name in CHECKED_NAMES


def _is_long_markdown_url(line: str, path: Path) -> bool:
    """Allow a standalone Markdown link target to exceed the width limit.

    Args:
        line: One physical line from a checked file.
        path: Source file that contains the line.
    """
    return path.suffix == ".md" and MARKDOWN_URL.fullmatch(line) is not None


def main() -> int:
    """Report lines wider than the repository's configured maximum.

    Returns:
        Zero when every checked line is within the limit, otherwise one.
    """
    root = Path(__file__).resolve().parents[1]
    violations: list[tuple[str, int, int]] = []
    for path in root.rglob("*"):
        if not path.is_file() or not _is_checked_file(path, root):
            continue
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if len(line) <= MAX_LINE_LENGTH:
                continue
            if _is_long_markdown_url(line, path):
                continue
            violations.append((
                path.relative_to(root).as_posix(),
                line_number,
                len(line),
            ))

    for relative_path, line_number, line_length in violations:
        print(f"{relative_path}:{line_number}: {line_length} characters")
    if violations:
        return 1
    print(f"All checked lines are at most {MAX_LINE_LENGTH} characters.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
