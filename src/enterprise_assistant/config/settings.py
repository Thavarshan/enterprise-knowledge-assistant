"""Load and validate environment-backed application settings.

Pydantic Settings reads `.env` and process environment variables, with the
process environment taking precedence. Secret-bearing values are excluded
from model representations. Defaults select local mock retrieval and
in-memory development authentication unless explicitly configured.
"""

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validate environment-backed application and provider settings.

    Pydantic Settings reads process variables before the local .env file.
    Secret values are excluded from model representations. Defaults select
    mock retrieval and development identity configuration.

    Attributes:
        app_name: FastAPI title and displayed product name.
        app_env: Deployment label such as development or test.
        mock_mode: Select fixture search when true.
        api_prefix: Prefix for versioned API routes.
        api_host: Stored bind setting; current launch commands bind directly.
        api_port: Stored field; the launcher reads API_PORT from the process.
        ui_port: Stored field; the launcher reads UI_PORT from the process.
        api_base_url: Default API URL for browser clients.
        memory_backend: Local SQLite or remote D1 gateway.
        sqlite_path: Local session database path.
        d1_api_url: HTTPS origin for the dedicated D1 Worker.
        d1_service_token: Backend-only credential for the D1 Worker.
        d1_timeout_seconds: Request timeout for the D1 Worker.
        auth_signing_secret: HMAC key for stateless access tokens.
        auth_issuer: Expected issuer in signed access tokens.
        auth_audience: Expected audience in signed access tokens.
        auth_token_ttl_seconds: Maximum bearer token lifetime.
        cors_origins: Browser origins allowed by FastAPI.
        log_level: Root structured-log level.
        rate_limit_capacity: Initial token-bucket capacity per user.
        rate_limit_refill_per_second: Per-user token refill rate.
        dev_users_json: Inline JSON or path to local development users.
        langsmith_tracing: Explicit opt-in for LangSmith tracing.
        langsmith_api_key: Secret used only when tracing is enabled.
        langsmith_endpoint: LangSmith Cloud API endpoint.
        langsmith_agent_id: Registered LangSmith agent identifier.
        langsmith_agent_environment: Target environment for agent traces.
        llm_provider: Mock or live provider used by supervisor and response.
        openai_api_key: Secret used by the optional OpenAI provider.
        openai_model: Model ID used for structured chat completions.
        llm_timeout_seconds: Maximum duration for one model request.
        pinecone_api_key: Secret used by the Pinecone document adapter.
        pinecone_index_name: Configured index name.
        pinecone_namespace: Optional configured namespace.
        pinecone_embedding_model: Pinecone inference model for dense vectors.
        pinecone_embedding_dimension: Dense dimension expected by the index.
        pinecone_timeout_seconds: Per-operation SDK timeout.
        pinecone_documents_path: Source JSON used for ingestion and BM25.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_name: str = "Viridian"
    app_env: str = "development"
    mock_mode: bool = True
    api_prefix: str = "/api/v1"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    ui_port: int = 8501
    api_base_url: str = "http://localhost:8000"
    memory_backend: Literal["sqlite", "d1"] = "sqlite"
    sqlite_path: str = "data/sessions.sqlite3"
    d1_api_url: str = Field(default="", repr=False)
    d1_service_token: str = Field(default="", repr=False)
    d1_timeout_seconds: int = Field(default=5, ge=1, le=30)
    auth_signing_secret: str = Field(default="", repr=False)
    auth_issuer: str = "viridian"
    auth_audience: str = "viridian-api"
    auth_token_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:8501"]
    )
    log_level: str = "INFO"
    rate_limit_capacity: int = Field(default=30, gt=0)
    rate_limit_refill_per_second: float = Field(default=0.5, gt=0)
    dev_users_json: str = Field(default="", repr=False)
    langsmith_tracing: bool = False
    langsmith_api_key: str = Field(default="", repr=False)
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_agent_id: str = "viridian"
    langsmith_agent_environment: str = "local"
    llm_provider: Literal["mock", "openai"] = "mock"
    openai_api_key: str = Field(default="", repr=False)
    openai_model: str = "gpt-4.1-mini"
    llm_timeout_seconds: int = Field(default=30, ge=1, le=120)
    pinecone_api_key: str = Field(default="", repr=False)
    pinecone_index_name: str = ""
    pinecone_namespace: str = ""
    pinecone_embedding_model: str = "llama-text-embed-v2"
    pinecone_embedding_dimension: int = Field(default=1024, gt=0)
    pinecone_timeout_seconds: int = Field(default=15, ge=1, le=60)
    pinecone_documents_path: str = "data/samples/incident_corpus.json"

    @field_validator("d1_api_url")
    @classmethod
    def validate_d1_api_url(cls, value: str) -> str:
        """Require D1 to use an absolute HTTP(S) origin without credentials.

        Args:
            value: Configured base URL for the authenticated Worker.

        Returns:
            The normalized origin without its trailing slash.

        Raises:
            ValueError: The value is not a plain HTTP(S) origin.
        """
        cleaned = value.strip()
        if not cleaned:
            return cleaned
        try:
            parsed = urlsplit(cleaned)
            valid = (
                parsed.scheme in {"http", "https"}
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
                and (parsed.port is None or 1 <= parsed.port <= 65535)
                and parsed.path in {"", "/"}
                and not parsed.query
                and not parsed.fragment
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("D1_API_URL must be an absolute HTTP(S) origin.")
        return cleaned.rstrip("/")

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, values: list[str]) -> list[str]:
        """Require every configured CORS entry to be an HTTP(S) origin.

        Args:
            values: Browser origins allowed by FastAPI middleware.

        Returns:
            Validated origins with trailing slashes removed.

        Raises:
            ValueError: An entry is malformed or contains a URL path.
        """
        origins: list[str] = []
        for value in values:
            cleaned = value.strip()
            parsed = urlsplit(cleaned)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or (parsed.port is not None and not 1 <= parsed.port <= 65535)
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "CORS_ORIGINS must contain absolute HTTP(S) origins."
                )
            origins.append(cleaned.rstrip("/"))
        return origins

    @model_validator(mode="after")
    def validate_deployment_profile(self) -> "Settings":
        """Reject incomplete or unsafe cloud deployment configuration.

        Cloud deployments require an explicitly selected D1 gateway,
        stateless signing key, and server-side credentials. Production can
        use deterministic mock mode or configured live providers.
        Local and test profiles keep their existing SQLite and mock defaults.

        Returns:
            This settings instance after profile validation.

        Raises:
            ValueError: A selected backend or production profile is missing
                mandatory configuration.
        """
        if self.memory_backend == "d1":
            if not self.d1_api_url or not self.d1_service_token:
                raise ValueError(
                    "MEMORY_BACKEND=d1 requires D1_API_URL and "
                    "D1_SERVICE_TOKEN."
                )
            if len(self.d1_service_token) < 32:
                raise ValueError(
                    "D1_SERVICE_TOKEN must contain at least 32 characters."
                )
            if self.app_env == "production" and not self.d1_api_url.startswith(
                "https://"
            ):
                raise ValueError("Production D1_API_URL must use HTTPS.")

        if self.app_env != "production":
            return self

        required_values = {
            "AUTH_SIGNING_SECRET": self.auth_signing_secret,
            "DEV_USERS_JSON": self.dev_users_json,
        }
        if self.langsmith_tracing:
            required_values["LANGSMITH_API_KEY"] = self.langsmith_api_key
        if not self.mock_mode:
            required_values.update(
                {
                    "OPENAI_API_KEY": self.openai_api_key,
                    "PINECONE_API_KEY": self.pinecone_api_key,
                    "PINECONE_INDEX_NAME": self.pinecone_index_name,
                }
            )
        missing = [name for name, value in required_values.items() if not value]
        if missing:
            raise ValueError(
                "Production configuration is missing: " + ", ".join(missing)
            )
        if len(self.auth_signing_secret) < 32:
            raise ValueError(
                "AUTH_SIGNING_SECRET must contain at least 32 characters."
            )
        if not self.dev_users_json.lstrip().startswith("{"):
            raise ValueError(
                "Production DEV_USERS_JSON must be inline JSON; "
                "filesystem user files are not available."
            )
        if self.memory_backend != "d1":
            raise ValueError("Production requires MEMORY_BACKEND=d1.")
        expected_provider = "mock" if self.mock_mode else "openai"
        if self.llm_provider != expected_provider:
            raise ValueError(
                "Production MOCK_MODE and LLM_PROVIDER must agree."
            )
        if not self.cors_origins or "*" in self.cors_origins:
            raise ValueError(
                "Production CORS_ORIGINS must contain explicit origins."
            )
        if any(
            not origin.startswith("https://") for origin in self.cors_origins
        ):
            raise ValueError("Production CORS origins must use HTTPS.")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings object used by app entrypoints.

    The one-entry cache avoids rereading environment configuration each time
    a dependency or factory asks for settings.

    Returns:
        Validated Settings instance.
    """
    return Settings()
