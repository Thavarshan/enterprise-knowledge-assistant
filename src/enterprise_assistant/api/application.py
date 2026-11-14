"""Assemble the FastAPI application and process-scoped service container.

The factory selects fixture or Pinecone retrieval, creates authentication,
SQLite memory, tool authorization, rate limiting, and the graph-backed chat
service, then registers routes and error handlers. SQLite initialization is
performed in the ASGI lifespan; other adapters are constructed at factory
time. Provider and credential values come from `Settings`.

The factory supports injected settings, memory, and retrievers so tests can
exercise request behavior without external providers.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from enterprise_assistant.api.errors import APIError
from enterprise_assistant.api.middleware import RequestIdMiddleware
from enterprise_assistant.api.routes import auth, chat, health
from enterprise_assistant.chat.service import ChatService
from enterprise_assistant.config.settings import Settings, get_settings
from enterprise_assistant.memory.interfaces import SessionStore
from enterprise_assistant.memory.sqlite import SQLiteSessionStore
from enterprise_assistant.observability.langsmith import (
    create_langsmith_address,
    create_langsmith_client,
)
from enterprise_assistant.observability.logging import configure_logging
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever
from enterprise_assistant.retrieval.interfaces import Retriever
from enterprise_assistant.retrieval.pinecone import (
    PineconeConfig,
    PineconeRetriever,
)
from enterprise_assistant.security.authentication import AuthService
from enterprise_assistant.security.rate_limiting import TokenBucketRateLimiter
from enterprise_assistant.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class AppContainer:
    """Hold process-scoped adapters and services for FastAPI.

    The factory stores one container on application state so route handlers
    share the same authentication token map, memory adapter, retriever, tool
    policy, rate limiter, and chat service. It is constructed once per app;
    injected memory and retrieval adapters support isolated tests.

    Attributes:
        settings: Validated configuration used to build the process.
        auth: Process-local development identity and token service.
        memory: Session persistence adapter shared by routes.
        retriever: Search adapter passed to the chat graph.
        tool_registry: Backend role policy for tool invocation.
        rate_limiter: Per-user, process-local request limiter.
        chat_service: Graph orchestration and turn persistence service.
    """
    settings: Settings
    auth: AuthService
    memory: SessionStore
    retriever: Retriever
    tool_registry: ToolRegistry
    rate_limiter: TokenBucketRateLimiter
    chat_service: ChatService


def create_app(
    settings: Settings | None = None,
    *,
    retriever: Retriever | None = None,
    memory: SessionStore | None = None,
) -> FastAPI:
    """Build the API and its process-scoped dependencies.

    Settings select mock fixture retrieval or the explicit Pinecone
    scaffold. The factory registers health and versioned API routes,
    request correlation, CORS, and safe exception responses. SQLite
    initialization runs in the lifespan hook, not during import.

    Args:
        settings: Optional validated settings; environment settings are
            loaded when omitted.
        retriever: Optional search adapter override for tests or embedding.
        memory: Optional session store override for tests or embedding.

    Returns:
        A configured FastAPI application with its service container attached.

    Notes:
        LangSmith setup uses the configured agent and environment address.
        Trace inputs and outputs are hidden, and only allowlisted metadata
        is exported. Service errors do not prevent API startup.
    """
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)
    langsmith_client = create_langsmith_client(app_settings)
    tracing_enabled = langsmith_client is not None
    langsmith_address = (
        create_langsmith_address(app_settings)
        if tracing_enabled
        else None
    )
    session_store = memory or SQLiteSessionStore(app_settings.sqlite_path)
    if retriever is not None:
        document_retriever = retriever
    elif app_settings.mock_mode:
        document_retriever = InMemoryRetriever.from_json()
    else:
        document_retriever = PineconeRetriever(
            PineconeConfig(
                api_key=app_settings.pinecone_api_key,
                index_name=app_settings.pinecone_index_name,
                namespace=app_settings.pinecone_namespace,
            )
        )
    registry = ToolRegistry()
    container = AppContainer(
        settings=app_settings,
        auth=AuthService(app_settings.dev_users_json),
        memory=session_store,
        retriever=document_retriever,
        tool_registry=registry,
        rate_limiter=TokenBucketRateLimiter(
            app_settings.rate_limit_capacity,
            app_settings.rate_limit_refill_per_second,
        ),
        chat_service=ChatService(
            document_retriever,
            session_store,
            registry,
            langsmith_client=langsmith_client,
            langsmith_address=langsmith_address,
        ),
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Initialize process resources for the ASGI lifetime.

        The synchronous store initializer creates SQLite tables before the
        application serves requests. There is no async database pool or
        explicit shutdown hook.

        Args:
            application: FastAPI instance entering its lifespan.

        Yields:
            Control to the ASGI server after initialization.
        """
        container.memory.initialize()
        logger.info(
            "Application startup complete",
            extra={"tracing_enabled": tracing_enabled,
                   "mock_mode": app_settings.mock_mode},
        )
        try:
            yield
        finally:
            if langsmith_client is not None:
                langsmith_client.close(timeout=5)

    application = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        description="Explainable enterprise knowledge assistant foundation.",
        lifespan=lifespan,
    )
    application.state.container = container
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    application.include_router(health.router)
    versioned = APIRouter(prefix=app_settings.api_prefix)
    versioned.include_router(auth.router)
    versioned.include_router(chat.router)
    application.include_router(versioned)

    @application.exception_handler(APIError)
    async def handle_api_error(
        _request: Request, exc: APIError
    ) -> JSONResponse:
        """Serialize a deliberate application error safely.

        The response contains only the status, stable code, and caller-safe
        message carried by APIError.

        Args:
            _request: Request associated with the exception; unused here.
            exc: Structured application error.

        Returns:
            JSON response with the error status and payload.
        """
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Return a safe summary of request validation failures.

        Only error types and locations are exposed; submitted values are
        omitted to avoid echoing credentials or other request content.

        Args:
            _request: Request associated with the invalid payload.
            exc: FastAPI validation error containing field locations.

        Returns:
            HTTP 422 JSON response with sanitized validation details.
        """
        errors = [{"type": error["type"], "loc": error["loc"]}
                  for error in exc.errors()]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "details": errors,
                }
            },
        )

    @application.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Normalize framework HTTP errors for API clients.

        Known status codes receive stable machine-readable codes. The
        framework status, safe string detail, and response headers are
        preserved.

        Args:
            _request: Request associated with the HTTP error.
            exc: Framework HTTP exception to translate.

        Returns:
            JSON response preserving the exception status and headers.
        """
        code = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            429: "rate_limited",
        }.get(exc.status_code, "http_error")
        detail = exc.detail if isinstance(
            exc.detail, str) else "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": detail}},
            headers=exc.headers,
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(
        _request: Request, exc: Exception
    ) -> JSONResponse:
        """Hide unexpected exception details from API responses.

        The handler logs the exception type and returns a generic HTTP 500
        payload. It intentionally does not include exception text or a
        traceback in the client response.

        Args:
            _request: Request associated with the failure.
            exc: Unexpected exception; only its type is logged.

        Returns:
            Generic internal-error JSON response.
        """
        logger.error("Unhandled API error", extra={
                     "error_type": type(exc).__name__})
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected server error occurred.",
                }
            },
        )

    return application
