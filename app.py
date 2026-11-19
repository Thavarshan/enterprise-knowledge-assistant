"""Expose FastAPI to Vercel's Python runtime.

Local Uvicorn and Vercel both build the application through the shared
factory in ``enterprise_assistant.api``.
"""

from enterprise_assistant.api.application import create_app

app = create_app()
