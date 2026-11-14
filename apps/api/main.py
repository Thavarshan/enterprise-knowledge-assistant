"""Create the ASGI application used by Uvicorn and Compose.

Importing this module builds the application through the shared factory,
which reads environment-backed settings and wires process-local services.
The module contains no route behavior so tests can construct isolated apps.
"""

from enterprise_assistant.api.application import create_app

app = create_app()
