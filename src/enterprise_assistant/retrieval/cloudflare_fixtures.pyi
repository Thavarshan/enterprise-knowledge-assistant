"""Typing contract for the fixture module staged during Worker builds.

The deployment helper generates the matching Python implementation from
``data/documents.json`` immediately before PyWrangler packages the Worker.
"""

from typing import Any

WORKER_DOCUMENTS: list[dict[str, Any]]
