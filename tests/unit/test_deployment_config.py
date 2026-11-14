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
from scripts.deployment.check_ci_gate import main as run_ci_gate
from scripts.deployment.cloudflare_config import database_matches
from scripts.deployment.policy import (
    deployment_blockers,
    failed_ci_jobs,
    release_is_current,
)
from scripts.deployment.validate_d1_migrations import (
    find_destructive_migrations,
)

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
    assert config["git"]["deploymentEnabled"] is False
    assert {
        "tests/**",
        "docs/**",
        "infra/**",
        "data/**",
        "scripts/**",
        "apps/ui/**",
        "apps/api/**",
    } <= ignored_paths


def test_ci_gate_fails_for_failed_cancelled_or_skipped_jobs() -> None:
    """Require success from every mandatory check result.

    Skipped and cancelled dependencies must block the aggregate CI gate.
    """
    failures = failed_ci_jobs({
        "lint": "success",
        "build": "failure",
        "tests": "cancelled",
        "docker-api-ui": "skipped",
    })

    assert failures == {
        "build": "failure",
        "tests": "cancelled",
        "docker-api-ui": "skipped",
    }


def test_ci_gate_command_exits_nonzero_for_incomplete_checks(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Make the actual gate command fail on unsuccessful job results.

    The workflow step must preserve failure, cancellation, and skip status.
    """
    monkeypatch.setenv(
        "CI_NEEDS_JSON",
        json.dumps({
            "lint": {"result": "success"},
            "tests": {"result": "cancelled"},
            "docker-api-ui": {"result": "skipped"},
        }),
    )

    assert run_ci_gate() == 1
    assert "tests=cancelled" in capsys.readouterr().out


def test_deployment_requires_successful_main_ci_and_explicit_opt_ins() -> None:
    """Block PR, scheduled, stale, disabled, and failed deployment runs.

    Automatic and manual paths must prove the current main SHA and CI success.
    """
    base = {
        "trigger": "workflow_run",
        "ref": "refs/heads/main",
        "upstream_event": "push",
        "upstream_branch": "main",
        "upstream_conclusion": "success",
        "manual_ci_result": "skipped",
        "deploy_enabled": True,
        "live_smoke_enabled": True,
        "release_sha": "a" * 40,
        "main_sha": "a" * 40,
    }
    assert deployment_blockers(**base) == []
    assert "The upstream CI workflow did not succeed." in deployment_blockers(
        **{**base, "upstream_conclusion": "cancelled"}
    )
    assert "Only successful pushes to main may deploy." in deployment_blockers(
        **{**base, "upstream_event": "pull_request"}
    )
    assert "Only successful pushes to main may deploy." in deployment_blockers(
        **{**base, "upstream_event": "schedule"}
    )
    assert "DEPLOY_ENABLED is not true." in deployment_blockers(
        **{**base, "deploy_enabled": False}
    )
    assert "The CI-approved release has been superseded on main." in (
        deployment_blockers(**{**base, "main_sha": "b" * 40})
    )
    assert "CI invoked by this manual run did not succeed." in (
        deployment_blockers(
            **{
                **base,
                "trigger": "workflow_dispatch",
                "manual_ci_result": "failure",
            }
        )
    )
    assert "Manual deployments must select main." in deployment_blockers(
        **{
            **base,
            "trigger": "workflow_dispatch",
            "ref": "refs/heads/feature",
        }
    )
    assert "RUN_LIVE_E2E_SMOKE is not true." in deployment_blockers(
        **{**base, "live_smoke_enabled": False}
    )


def test_release_current_check_requires_exact_sha_match() -> None:
    """Prevent stale deployment jobs from mutating cloud resources.

    The workflow must stop when a newer commit advances the main branch.
    """
    assert release_is_current("a" * 40, "a" * 40)
    assert not release_is_current("a" * 40, "b" * 40)


def test_cloudflare_identity_must_match_name_and_complete_id() -> None:
    """Reject an account response that names the wrong D1 database.

    Matching the dedicated name alone is insufficient without the exact UUID.
    """
    payload = {
        "success": True,
        "result": [{
            "name": "eka-assessment-d1",
            "uuid": "12345678-1234-1234-1234-123456789abc",
        }],
    }

    assert database_matches(
        payload,
        "eka-assessment-d1",
        "12345678-1234-1234-1234-123456789abc",
    )
    assert not database_matches(
        payload,
        "eka-assessment-d1",
        "12345678-1234-1234-1234-123456789abd",
    )
    assert not database_matches(
        payload,
        "another-database",
        "12345678-1234-1234-1234-123456789abc",
    )


def test_migration_validator_rejects_destructive_sql_and_ignores_comments(
    tmp_path: Path,
) -> None:
    """Reject table drops while allowing explanatory SQL comments.

    Only executable migration statements are considered by the safety check.
    """
    (tmp_path / "0001_create.sql").write_text(
        "-- DROP TABLE is unsafe\nCREATE TABLE safe (id INTEGER);",
        encoding="utf-8",
    )
    assert find_destructive_migrations(tmp_path) == []
    (tmp_path / "0002_drop.sql").write_text(
        "DROP TABLE safe;",
        encoding="utf-8",
    )
    assert find_destructive_migrations(tmp_path) == [
        ("0002_drop.sql", "DROP statements"),
    ]
