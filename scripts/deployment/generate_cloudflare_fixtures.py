"""Stage fixture records as Python source for the Workers bundle.

PyWrangler packages Python modules but does not include the JSON source file.
"""

import json
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE = (
    REPOSITORY_ROOT / "src/enterprise_assistant/retrieval/data/documents.json"
)
DESTINATION = (
    REPOSITORY_ROOT
    / "src/enterprise_assistant/retrieval/cloudflare_fixtures.py"
)


def prepare_worker_fixtures() -> Path:
    """Generate an importable fixture module from the checked-in JSON file.

    Returns:
        The generated Python module staged for the Wrangler build.
    """
    records: Any = json.loads(SOURCE.read_text(encoding="utf-8"))
    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        raise ValueError("The Worker fixture source must be a JSON array.")
    compact_json = json.dumps(records, separators=(",", ":"))
    module = (
        '"""Generated from retrieval/data/documents.json for Workers."""\n\n'
        "import json\n\n"
        f"WORKER_DOCUMENTS = json.loads({compact_json!r})\n"
    )
    DESTINATION.write_text(module, encoding="utf-8")
    return DESTINATION


def remove_worker_fixtures() -> None:
    """Remove the generated module after the Worker build completes.

    Missing files are ignored so cleanup is safe after a failed staging step.
    """
    try:
        DESTINATION.unlink()
    except FileNotFoundError:
        pass


def main() -> int:
    """Stage checked-in fixture data for local bundle validation.

    Returns:
        Zero when the module is generated, otherwise one.
    """
    try:
        path = prepare_worker_fixtures()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Cloudflare fixture preparation failed: {exc}")
        return 1
    print(f"Prepared Worker fixture module: {path.name}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
