"""Assemble the FastAPI application and process-scoped service container.

The factory selects fixture or Pinecone retrieval, configured SQLite or D1
memory, authentication, authorization, rate limiting, and graph-backed chat.
Storage initialization and adapter shutdown run in the ASGI lifespan.
Provider and credential values come from validated application settings.

The factory supports injected settings, memory, and retrievers so tests can
exercise request behavior without external providers.
"""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from enterprise_assistant.api.errors import APIError
from enterprise_assistant.api.middleware import RequestIdMiddleware
from enterprise_assistant.api.routes import auth, chat, health
from enterprise_assistant.config.settings import Settings, get_settings
from enterprise_assistant.llm.contracts import ModelProvider
from enterprise_assistant.memory.d1 import SessionStoreUnavailable
from enterprise_assistant.memory.factory import create_session_store
from enterprise_assistant.memory.interfaces import SessionStore
from enterprise_assistant.observability.logging import configure_logging
from enterprise_assistant.retrieval.hybrid import HybridRetriever
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever
from enterprise_assistant.retrieval.interfaces import Retriever
from enterprise_assistant.security.authentication import AuthService
from enterprise_assistant.security.guardrails import PromptInjectionGuardrail
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
        auth: Password verifier and signed-token issuer and verifier.
        memory: Session persistence adapter shared by routes.
        retriever: Search adapter passed to the chat graph.
        tool_registry: Backend role policy for tool invocation.
        input_guardrail: Input filter called before user message persistence.
        rate_limiter: Per-user, process-local request limiter.
        model_provider: Structured provider used by graph agents.
        chat_service: Graph orchestration and turn persistence service.
    """

    settings: Settings
    auth: AuthService
    memory: SessionStore
    retriever: Retriever
    tool_registry: ToolRegistry
    input_guardrail: PromptInjectionGuardrail
    rate_limiter: TokenBucketRateLimiter
    model_provider: ModelProvider | None
    chat_service: Any


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
        Trace payloads are visible with recognized credentials anonymized.
        Service errors do not prevent API startup.
    """
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)
    cloudflare_worker = os.environ.get("CLOUDFLARE_WORKER") == "true"
    if cloudflare_worker:
        model_provider = None
        langsmith_client = None
        langsmith_address = None
    else:
        from enterprise_assistant.llm.providers import create_model_provider
        from enterprise_assistant.observability.langsmith import (
            create_langsmith_address,
            create_langsmith_client,
        )

        model_provider = create_model_provider(app_settings)
        langsmith_client = create_langsmith_client(app_settings)
        langsmith_address = (
            create_langsmith_address(app_settings)
            if langsmith_client is not None
            else None
        )
    tracing_enabled = langsmith_client is not None
    session_store = memory or create_session_store(app_settings)
    if retriever is not None:
        document_retriever = retriever
    elif cloudflare_worker:
        if not app_settings.mock_mode:
            raise ValueError("The Cloudflare Worker requires mock mode.")
        from enterprise_assistant.retrieval.cloudflare_fixtures import (
            WORKER_DOCUMENTS,
        )

        document_retriever = InMemoryRetriever.from_records(WORKER_DOCUMENTS)
    elif app_settings.mock_mode:
        document_retriever = InMemoryRetriever.from_json()
    else:
        from enterprise_assistant.retrieval.pinecone import (
            PineconeConfig,
            PineconeRetriever,
        )

        pinecone_retriever = PineconeRetriever(
            PineconeConfig(
                api_key=app_settings.pinecone_api_key,
                index_name=app_settings.pinecone_index_name,
                namespace=app_settings.pinecone_namespace,
                embedding_model=app_settings.pinecone_embedding_model,
                embedding_dimension=(app_settings.pinecone_embedding_dimension),
                timeout_seconds=app_settings.pinecone_timeout_seconds,
            )
        )
        document_retriever = HybridRetriever(
            pinecone_retriever,
            pinecone_retriever,
        )
    registry = ToolRegistry()
    chat_service: Any
    if cloudflare_worker:
        from enterprise_assistant.chat.workers_service import (
            WorkersMockChatService,
        )

        chat_service = WorkersMockChatService(
            document_retriever,
            session_store,
        )
    else:
        from enterprise_assistant.chat.service import ChatService

        chat_service = ChatService(
            document_retriever,
            session_store,
            registry,
            langsmith_client=langsmith_client,
            langsmith_address=langsmith_address,
            model_provider=model_provider,
        )
    container = AppContainer(
        settings=app_settings,
        auth=AuthService(
            app_settings.dev_users_json,
            signing_secret=app_settings.auth_signing_secret or None,
            issuer=app_settings.auth_issuer,
            audience=app_settings.auth_audience,
            token_ttl_seconds=app_settings.auth_token_ttl_seconds,
        ),
        memory=session_store,
        retriever=document_retriever,
        tool_registry=registry,
        input_guardrail=PromptInjectionGuardrail(),
        rate_limiter=TokenBucketRateLimiter(
            app_settings.rate_limit_capacity,
            app_settings.rate_limit_refill_per_second,
        ),
        model_provider=model_provider,
        chat_service=chat_service,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Initialize process resources for the ASGI lifetime.

        The configured store initializes once before serving requests.
        SQLite work is thread-offloaded by its adapter; D1 checks Worker
        readiness asynchronously. Reusable HTTP clients close on shutdown.

        Args:
            application: FastAPI instance entering its lifespan.

        Yields:
            Control to the ASGI server after initialization.
        """
        try:
            await container.memory.initialize()
            logger.info(
                "Application startup complete",
                extra={
                    "tracing_enabled": tracing_enabled,
                    "mock_mode": app_settings.mock_mode,
                    "memory_backend": app_settings.memory_backend,
                },
            )
            yield
        finally:
            close_store = getattr(container.memory, "aclose", None)
            if close_store is not None:
                await close_store()
            if langsmith_client is not None:
                langsmith_client.close(timeout=5)
            if model_provider is not None:
                await model_provider.aclose()

    application = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        description="Viridian's explainable AI assistant API.",
        lifespan=lifespan,
    )
    application.state.container = container
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=False,
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

    @application.exception_handler(SessionStoreUnavailable)
    async def handle_storage_error(
        _request: Request, _exc: SessionStoreUnavailable
    ) -> JSONResponse:
        """Return a stable response when the selected store is unavailable.

        The provider exception is deliberately excluded from the response so
        URLs, service credentials, and remote error bodies cannot leak.

        Args:
            _request: Request associated with the storage failure.
            _exc: Internal safe-storage exception; details are not exposed.

        Returns:
            A caller-safe HTTP 503 response.
        """
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "session_store_unavailable",
                    "message": "Conversation storage is unavailable.",
                }
            },
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
        errors = [
            {"type": error["type"], "loc": error["loc"]}
            for error in exc.errors()
        ]
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
        detail = (
            exc.detail if isinstance(exc.detail, str) else "Request failed."
        )
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
        logger.error(
            "Unhandled API error", extra={"error_type": type(exc).__name__}
        )
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
