"""FastAPI application factory with explicit dependencies and clean lifespan."""

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
from enterprise_assistant.observability.langsmith import configure_langsmith
from enterprise_assistant.observability.logging import configure_logging
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever
from enterprise_assistant.retrieval.interfaces import Retriever
from enterprise_assistant.retrieval.pinecone import PineconeConfig, PineconeRetriever
from enterprise_assistant.security.authentication import AuthService
from enterprise_assistant.security.rate_limiting import TokenBucketRateLimiter
from enterprise_assistant.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class AppContainer:
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
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)
    tracing_enabled = configure_langsmith(app_settings)
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
        chat_service=ChatService(document_retriever, session_store, registry),
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        container.memory.initialize()
        logger.info(
            "Application startup complete",
            extra={"tracing_enabled": tracing_enabled, "mock_mode": app_settings.mock_mode},
        )
        yield

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
    async def handle_api_error(_request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [{"type": error["type"], "loc": error["loc"]} for error in exc.errors()]
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
    async def handle_http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            429: "rate_limited",
        }.get(exc.status_code, "http_error")
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": detail}},
            headers=exc.headers,
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled API error", extra={"error_type": type(exc).__name__})
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
