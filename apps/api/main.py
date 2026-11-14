"""ASGI entrypoint used by Uvicorn and Docker Compose."""

from enterprise_assistant.api.application import create_app

app = create_app()
