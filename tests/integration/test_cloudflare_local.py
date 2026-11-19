"""Exercise FastAPI persistence through a local Wrangler and D1 instance.

The opt-in test starts a Worker with local-only migrations and a disposable
database. It drives authentication, graph execution, restart recovery, and
owner isolation through the public FastAPI routes.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from enterprise_assistant.api.application import create_app
from enterprise_assistant.config.settings import Settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKER_ROOT = REPOSITORY_ROOT / "infra/cloudflare/d1-gateway"
SERVICE_TOKEN = "local-test-service-token-not-a-secret-00000000"
SIGNING_SECRET = "local-test-signing-secret-not-a-secret-00000000"
USERS = {
    "analyst": {
        "password": "local-test-analyst-password",
        "role": "analyst",
    },
    "viewer": {
        "password": "local-test-viewer-password",
        "role": "viewer",
    },
}


def _free_port() -> int:
    """Reserve and return an unused loopback TCP port number.

    Returns:
        A port that was available when this helper checked the socket.
    """
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _copy_worker_project(destination: Path) -> None:
    """Copy Worker sources and link installed packages into a test sandbox.

    Args:
        destination: Temporary project directory for Wrangler's local state.
    """
    for name in ("migrations", "src"):
        shutil.copytree(WORKER_ROOT / name, destination / name)
    for name in ("package.json", "package-lock.json", "wrangler.jsonc"):
        shutil.copy2(WORKER_ROOT / name, destination / name)
    (destination / "node_modules").symlink_to(
        WORKER_ROOT / "node_modules",
        target_is_directory=True,
    )
    (destination / ".dev.vars").write_text(
        f"D1_SERVICE_TOKEN={SERVICE_TOKEN}\n",
        encoding="utf-8",
    )


def _start_worker(
    project: Path,
    persist_path: Path,
    port: int,
) -> tuple[subprocess.Popen[bytes], Path]:
    """Apply only local migrations and start Wrangler in local mode.

    Args:
        project: Temporary Worker project with the local test secret.
        persist_path: Disposable local D1 state directory.
        port: Loopback port to expose for the test process.

    Returns:
        Running Wrangler process and the file containing its diagnostic log.
    """
    wrangler = WORKER_ROOT / "node_modules/.bin/wrangler"
    environment = {**os.environ, "WRANGLER_SEND_METRICS": "false"}
    migration = subprocess.run(
        [
            str(wrangler),
            "d1",
            "migrations",
            "apply",
            "viridian-sessions",
            "--local",
            "--persist-to",
            str(persist_path),
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if migration.returncode != 0:
        pytest.fail(
            "Local D1 migration failed:\n"
            + migration.stdout
            + migration.stderr
        )

    log_path = project / "wrangler.log"
    with log_path.open("wb") as log_file:
        process = subprocess.Popen(
            [
                str(wrangler),
                "dev",
                "--local",
                "--persist-to",
                str(persist_path),
                "--ip",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=project,
            env=environment,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    return process, log_path


def _wait_for_worker(
    process: subprocess.Popen[bytes],
    base_url: str,
    log_path: Path,
) -> None:
    """Wait for the authenticated local D1 readiness route.

    Args:
        process: Wrangler process whose exit state is monitored.
        base_url: Loopback address of the local Worker.
        log_path: File containing Wrangler startup diagnostics.

    Raises:
        AssertionError: Wrangler exits or does not become ready in time.
    """
    headers = {"Authorization": f"Bearer {SERVICE_TOKEN}"}
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = log_path.read_text(encoding="utf-8", errors="replace")
            pytest.fail(f"Wrangler exited during startup:\n{output}")
        try:
            response = httpx.get(
                f"{base_url}/internal/ready",
                headers=headers,
                timeout=1,
            )
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    output = log_path.read_text(encoding="utf-8", errors="replace")
    pytest.fail(f"Local D1 Worker did not become ready:\n{output}")


def _settings(worker_url: str) -> Settings:
    """Build deterministic cloud-style settings without a local env file.

    Args:
        worker_url: URL of the authenticated local Worker.

    Returns:
        Test settings using mock retrieval and D1 persistence.
    """
    return Settings(
        _env_file=None,
        app_env="test",
        mock_mode=True,
        llm_provider="mock",
        memory_backend="d1",
        d1_api_url=worker_url,
        d1_service_token=SERVICE_TOKEN,
        auth_signing_secret=SIGNING_SECRET,
        auth_issuer="local-cloud-simulation",
        auth_audience="local-cloud-simulation-api",
        dev_users_json=json.dumps(USERS),
        cors_origins=[],
        langsmith_tracing=False,
        sqlite_path="unused/sessions.sqlite3",
    )


@pytest.mark.integration
def test_local_worker_d1_survives_api_restart_and_scopes_owners(
    tmp_path: Path,
) -> None:
    """Verify the local API-to-D1 path without external cloud access.

    Args:
        tmp_path: Pytest-owned directory for the Worker and D1 state.
    """
    if os.environ.get("RUN_D1_WORKER_TESTS") != "true":
        pytest.skip("Set RUN_D1_WORKER_TESTS=true to start local Wrangler.")

    project = tmp_path / "worker"
    project.mkdir()
    _copy_worker_project(project)
    persist_path = tmp_path / "local-d1"
    port = _free_port()
    process, log_path = _start_worker(project, persist_path, port)
    worker_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_worker(process, worker_url, log_path)
        settings = _settings(worker_url)
        app = create_app(settings)
        with TestClient(app) as first_backend:
            login = first_backend.post(
                "/api/v1/auth/token",
                json={
                    "username": "analyst",
                    "password": USERS["analyst"]["password"],
                },
            )
            assert login.status_code == 200
            analyst_headers = {
                "Authorization": f"Bearer {login.json()['access_token']}"
            }
            created = first_backend.post(
                "/api/v1/chat/sessions",
                json={"title": "D1 deployment simulation"},
                headers=analyst_headers,
            )
            assert created.status_code == 201
            session_id = created.json()["session_id"]
            turn = first_backend.post(
                "/api/v1/chat/stream",
                json={
                    "session_id": session_id,
                    "message": "What happened in incident INC-2026-057?",
                },
                headers=analyst_headers,
            )
            assert turn.status_code == 200
            assert "event: response_chunk" in turn.text
            assert "event: retrieval" in turn.text
            assert "event: validation" in turn.text
            history = first_backend.get(
                f"/api/v1/chat/sessions/{session_id}",
                headers=analyst_headers,
            )
            assert history.status_code == 200
            expected_messages = history.json()["messages"]
            assert [message["role"] for message in expected_messages] == [
                "user",
                "assistant",
            ]
            assert expected_messages[-1]["content"]

        restarted_backend = create_app(settings)
        with TestClient(restarted_backend) as second_backend:
            recovered = second_backend.get(
                f"/api/v1/chat/sessions/{session_id}",
                headers=analyst_headers,
            )
            assert recovered.status_code == 200
            assert recovered.json()["messages"] == expected_messages
            viewer_login = second_backend.post(
                "/api/v1/auth/token",
                json={
                    "username": "viewer",
                    "password": USERS["viewer"]["password"],
                },
            )
            assert viewer_login.status_code == 200
            viewer_headers = {
                "Authorization": (
                    f"Bearer {viewer_login.json()['access_token']}"
                )
            }
            foreign = second_backend.get(
                f"/api/v1/chat/sessions/{session_id}",
                headers=viewer_headers,
            )
            assert foreign.status_code == 404

            process.terminate()
            process.wait(timeout=10)
            unavailable = second_backend.get("/ready")
            assert unavailable.status_code == 503
            assert "D1_SERVICE_TOKEN" not in unavailable.text
        assert not (tmp_path / "unused").exists()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
