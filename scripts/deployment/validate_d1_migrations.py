"""Reject destructive SQL before it can reach a remote D1 database.

This conservative source check allows forward-compatible additive changes
and blocks table drops, truncation, destructive alters, and row deletion.
"""

import re
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_ROOT = REPOSITORY_ROOT / "infra/cloudflare/d1-gateway/migrations"
COMMENT_PATTERN = re.compile(r"/\*.*?\*/|--[^\n]*", re.DOTALL)
DESTRUCTIVE_PATTERNS = {
    "DROP statements": re.compile(
        r"\bDROP\s+(TABLE|INDEX|DATABASE|VIEW)\b",
        re.I,
    ),
    "TRUNCATE statements": re.compile(r"\bTRUNCATE\b", re.I),
    "ALTER TABLE DROP": re.compile(
        r"\bALTER\s+TABLE\b[^;]*\bDROP\b", re.I | re.DOTALL
    ),
    "DELETE statements": re.compile(r"\bDELETE\s+FROM\b", re.I),
}


def find_destructive_migrations(
    migration_root: Path,
) -> list[tuple[str, str]]:
    """Find destructive DDL or row deletion in all tracked SQL migrations.

    Args:
        migration_root: Directory containing ordered SQL migration files.

    Returns:
        Migration filename and the matching forbidden operation name.
    """
    problems: list[tuple[str, str]] = []
    for path in sorted(migration_root.glob("*.sql")):
        sql = COMMENT_PATTERN.sub(" ", path.read_text(encoding="utf-8"))
        for label, pattern in DESTRUCTIVE_PATTERNS.items():
            if pattern.search(sql):
                problems.append((path.name, label))
    return problems


def main() -> int:
    """Validate migration file naming and forbid destructive operations.

    Returns:
        Zero when every migration is additive and has a stable numeric prefix.
    """
    migrations = sorted(MIGRATION_ROOT.glob("*.sql"))
    if not migrations:
        print("No D1 migrations were found.")
        return 1
    invalid_names = [
        path.name
        for path in migrations
        if not re.match(r"^\d{4}_[a-z0-9_]+\.sql$", path.name)
    ]
    duplicate_prefixes = len({path.name[:4] for path in migrations}) != len(
        migrations
    )
    problems = find_destructive_migrations(MIGRATION_ROOT)
    if invalid_names or duplicate_prefixes or problems:
        for name in invalid_names:
            print(f"Invalid migration filename: {name}")
        if duplicate_prefixes:
            print("D1 migration sequence numbers must be unique.")
        for filename, operation in problems:
            print(f"Rejected {operation} in {filename}.")
        return 1
    print(f"Validated {len(migrations)} additive D1 migration(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
