"""Environment-backed settings shared by the API and local tooling."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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
    langsmith_project: str = "enterprise-knowledge-assistant"
    pinecone_api_key: str = Field(default="", repr=False)
    pinecone_index_name: str = ""
    pinecone_namespace: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached process settings for application entrypoints."""
    return Settings()
