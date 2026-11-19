"""Verify cloud configuration selection and deployment entrypoints.

These tests check provider wiring without connecting to deployed services.
"""

import asyncio
import json
from pathlib import Path

import pytest
from apps.ui.services.config import resolve_api_base_url
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

    Local environment overrides still take precedence over the deployment
    default.
    """
    assert resolve_api_base_url(
        {"API_BASE_URL": "https://api.example/"},
        {"API_BASE_URL": "https://secret.example"},
    ) == "https://api.example"
    assert resolve_api_base_url(
        {},
        {"API_BASE_URL": "https://secret.example/"},
    ) == "https://secret.example"
    assert resolve_api_base_url({}, {}) == (
        "https://viridian.thavarshan.workers.dev"
    )


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


def test_cloudflare_python_worker_uses_viridian_assets_and_mock_mode() -> None:
    """Keep the Cloudflare API bound to the static Viridian frontend."""
    repository_root = Path(__file__).resolve().parents[2]
    config = json.loads((repository_root / "wrangler.jsonc").read_text())
    entrypoint = (
        repository_root / "infra/cloudflare/viridian-api/entry.py"
    ).read_text()

    assert config["name"] == "viridian"
    assert config["compatibility_flags"] == ["python_workers"]
    assert config["vars"]["MOCK_MODE"] == "true"
    assert config["vars"]["LLM_PROVIDER"] == "mock"
    assert config["vars"]["LANGSMITH_TRACING"] == "false"
    assert config["assets"]["binding"] == "ASSETS"
    assert "/api/*" in config["assets"]["run_worker_first"]
    assert "from workers import asgi, env" in entrypoint
    assert "Default = asgi.entrypoint(app)" in entrypoint
    assert not (repository_root / "vercel.json").exists()


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


def test_deployment_requires_successful_main_ci_without_opt_ins() -> None:
    """Block PR, scheduled, stale, and failed deployment runs.

    Automatic and manual paths must prove the current main SHA and CI success.
    """
    base = {
        "trigger": "push",
        "ref": "refs/heads/main",
        "ci_result": "success",
        "release_sha": "a" * 40,
        "main_sha": "a" * 40,
    }
    assert deployment_blockers(**base) == []
    assert "The mandatory CI gate did not succeed." in deployment_blockers(
        **{**base, "ci_result": "cancelled"}
    )
    assert "Only successful pushes to main may deploy." in deployment_blockers(
        **{**base, "ref": "refs/heads/feature"}
    )
    assert "This workflow event is not a deployment trigger." in (
        deployment_blockers(**{**base, "trigger": "schedule"})
    )
    assert "The CI-approved release has been superseded on main." in (
        deployment_blockers(**{**base, "main_sha": "b" * 40})
    )
    assert "The mandatory CI gate did not succeed." in (
        deployment_blockers(
            **{
                **base,
                "trigger": "workflow_dispatch",
                "ci_result": "failure",
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
            "name": "viridian-sessions",
            "uuid": "12345678-1234-1234-1234-123456789abc",
        }],
    }

    assert database_matches(
        payload,
        "viridian-sessions",
        "12345678-1234-1234-1234-123456789abc",
    )
    assert not database_matches(
        payload,
        "viridian-sessions",
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
