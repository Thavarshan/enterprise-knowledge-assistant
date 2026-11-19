"""Expose the Viridian FastAPI application as a Cloudflare Python Worker."""

import os

from workers import asgi, env

from enterprise_assistant.api.application import create_app

_RUNTIME_SETTINGS = (
    "APP_ENV",
    "APP_NAME",
    "APP_RELEASE_SHA",
    "AUTH_AUDIENCE",
    "AUTH_ISSUER",
    "AUTH_SIGNING_SECRET",
    "CLOUDFLARE_WORKER",
    "CORS_ORIGINS",
    "D1_API_URL",
    "D1_SERVICE_TOKEN",
    "D1_TIMEOUT_SECONDS",
    "DEV_USERS_JSON",
    "LANGSMITH_TRACING",
    "LLM_PROVIDER",
    "MEMORY_BACKEND",
    "MOCK_MODE",
)
for _name in _RUNTIME_SETTINGS:
    _value = getattr(env, _name, None)
    if _value is not None:
        os.environ[_name] = str(_value)

app = create_app()
Default = asgi.entrypoint(app)
