"""Expose FastAPI to Vercel's Python runtime.

Local Uvicorn and Vercel both build the application through the shared
factory in ``enterprise_assistant.api``.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from enterprise_assistant.api.application import create_app

app = create_app()
