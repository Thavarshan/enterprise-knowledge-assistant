"""Load and validate environment-backed application settings.

Pydantic Settings reads `.env` and process environment variables, with the
process environment taking precedence. Secret-bearing values are excluded
from model representations. Defaults select local mock retrieval and
in-memory development authentication unless explicitly configured.
"""

from functools import lru_cache

from pydantic import Field
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
        api_base_url: Default API URL; Streamlit reads its process environment.
        sqlite_path: Local session database path.
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
        pinecone_api_key: Secret reserved for the Pinecone adapter.
        pinecone_index_name: Configured index name.
        pinecone_namespace: Optional configured namespace.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_name: str = "Enterprise Knowledge Assistant"
    app_env: str = "development"
    mock_mode: bool = True
    api_prefix: str = "/api/v1"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    ui_port: int = 8501
    api_base_url: str = "http://localhost:8000"
    sqlite_path: str = "data/sessions.sqlite3"
    cors_origins: list[str] = Field(default_factory=lambda: [
                                    "http://localhost:8501"])
    log_level: str = "INFO"
    rate_limit_capacity: int = Field(default=30, gt=0)
    rate_limit_refill_per_second: float = Field(default=0.5, gt=0)
    dev_users_json: str = Field(default="", repr=False)
    langsmith_tracing: bool = False
    langsmith_api_key: str = Field(default="", repr=False)
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_agent_id: str = "enterprise-knowledge-assistant"
    langsmith_agent_environment: str = "local"
    pinecone_api_key: str = Field(default="", repr=False)
    pinecone_index_name: str = ""
    pinecone_namespace: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings object used by app entrypoints.

    The one-entry cache avoids rereading environment configuration each time
    a dependency or factory asks for settings.

    Returns:
        Validated Settings instance.
    """
    return Settings()
