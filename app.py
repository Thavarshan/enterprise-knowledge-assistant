"""Expose the existing FastAPI factory to Vercel's Python runtime.

This entrypoint contains no route or provider logic. Local Uvicorn and Vercel
both build the same application through ``enterprise_assistant.api``.
"""

from enterprise_assistant.api.application import create_app

app = create_app()
