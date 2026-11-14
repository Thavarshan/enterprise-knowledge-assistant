"""Verify cloud configuration selection and deployment entrypoints.

These tests check provider wiring without connecting to deployed services.
"""

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest
from apps.ui.services.config import resolve_api_base_url
from fastapi import FastAPI

from enterprise_assistant.config.settings import Settings
from enterprise_assistant.memory.d1 import D1SessionStore
from enterprise_assistant.memory.factory import create_session_store


def test_api_base_url_reads_environment_before_streamlit_secrets() -> None:
    """Prefer an environment override and support Streamlit secrets.

    Local defaults remain available for the development environment.
    """
    assert resolve_api_base_url(
        {"API_BASE_URL": "https://api.example/"},
        {"API_BASE_URL": "https://secret.example"},
    ) == "https://api.example"
    assert resolve_api_base_url(
        {},
        {"API_BASE_URL": "https://secret.example/"},
    ) == "https://secret.example"
    assert resolve_api_base_url({}, {}) == "http://localhost:8000"


def test_api_base_url_rejects_invalid_values() -> None:
    """Reject malformed origins before making an HTTP request.

    The UI must not forward credentials or ignored path components from
    a copied URL into backend requests.
    """
    with pytest.raises(ValueError):
        resolve_api_base_url({"API_BASE_URL": "javascript:alert(1)"}, {})
    with pytest.raises(ValueError):
        resolve_api_base_url(
            {"API_BASE_URL": "https://user:secret@api.example"},
            {},
        )


def test_production_settings_fail_closed_without_cloud_secrets() -> None:
    """Require explicit live backend and identity settings in production.

    Missing settings must fail validation before application startup.
    """
    with pytest.raises(ValueError, match="Production configuration"):
        Settings(_env_file=None, app_env="production")


def test_production_rejects_missing_d1_configuration() -> None:
    """Do not fall back to SQLite when D1 mode lacks its configuration.

    Cloud mode must fail closed when its remote store is not configured.
    """
    with pytest.raises(ValueError, match="D1_API_URL"):
        Settings(_env_file=None, memory_backend="d1")


def test_d1_url_and_cors_reject_non_origin_values() -> None:
    """Reject malformed URLs before they reach clients or middleware.

    Both provider endpoints and browser origins must be plain URL origins.
    """
    with pytest.raises(ValueError, match="D1_API_URL"):
        Settings(
            _env_file=None,
            memory_backend="d1",
            d1_api_url="https://worker.example/api",
            d1_service_token="local-test-token-with-at-least-32-characters",
        )
    with pytest.raises(ValueError, match="D1_API_URL"):
        Settings(
            _env_file=None,
            memory_backend="d1",
            d1_api_url="https://worker.example:invalid",
            d1_service_token="local-test-token-with-at-least-32-characters",
        )
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(
            _env_file=None,
            cors_origins=["https://example.test/path"],
        )


def test_cloud_factory_selects_d1_without_creating_local_storage(
    tmp_path: Path,
) -> None:
    """Build D1 directly and keep SQLite inactive in cloud mode.

    Constructing the remote adapter must not create the local database path.
    """
    settings = Settings(
        _env_file=None,
        memory_backend="d1",
        d1_api_url="https://worker.example",
        d1_service_token="local-test-token-with-at-least-32-characters",
        sqlite_path=str(tmp_path / "unused" / "sessions.sqlite3"),
    )
    store = create_session_store(settings)

    assert isinstance(store, D1SessionStore)
    assert not Path(settings.sqlite_path).parent.exists()
    asyncio.run(store.aclose())


def test_vercel_entrypoint_imports_shared_fastapi_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Import root entrypoint with cloud storage and no local SQLite writes.

    The isolated working directory ensures deployment import behavior does
    not depend on the developer's local environment file or account file.
    """
    from enterprise_assistant.config.settings import get_settings

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MOCK_MODE", "false")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("MEMORY_BACKEND", "d1")
    monkeypatch.setenv("D1_API_URL", "https://worker.example")
    monkeypatch.setenv(
        "D1_SERVICE_TOKEN",
        "local-test-token-with-at-least-32-characters",
    )
    monkeypatch.setenv(
        "DEV_USERS_JSON",
        json.dumps({
            "analyst": {
                "password": "synthetic-password",
                "role": "analyst",
            }
        }),
    )
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    get_settings.cache_clear()

    repository_root = Path(__file__).resolve().parents[2]
    entrypoint = repository_root / "app.py"
    spec = importlib.util.spec_from_file_location(
        "vercel_fastapi_entrypoint",
        entrypoint,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert isinstance(module.app, FastAPI)
    assert isinstance(module.app.state.container.memory, D1SessionStore)
    assert not (tmp_path / "data").exists()
    asyncio.run(module.app.state.container.memory.aclose())
    get_settings.cache_clear()


def test_vercel_config_limits_duration_and_excludes_non_runtime_files() -> None:
    """Keep the Vercel Function bounded and its bundle focused.

    The runtime should include the shared FastAPI entrypoint and source while
    excluding UI, tests, fixtures, documentation, and infrastructure.
    """
    repository_root = Path(__file__).resolve().parents[2]
    config = json.loads((repository_root / "vercel.json").read_text())
    ignored_paths = set(
        (repository_root / ".vercelignore").read_text().splitlines()
    )

    assert config["functions"]["app.py"]["maxDuration"] == 60
    assert {
        "tests/**",
        "docs/**",
        "infra/**",
        "data/**",
        "scripts/**",
        "apps/ui/**",
        "apps/api/**",
    } <= ignored_paths
