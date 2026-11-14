"""Shared deterministic application fixtures."""

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from enterprise_assistant.api.application import create_app
from enterprise_assistant.config.settings import Settings

TEST_USERS = {
    "viewer": {"password": "viewer-test-password", "role": "viewer"},
    "analyst": {"password": "analyst-test-password", "role": "analyst"},
    "admin": {"password": "admin-test-password", "role": "administrator"},
}


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        app_env="test",
        mock_mode=True,
        sqlite_path=str(tmp_path / "sessions.sqlite3"),
        cors_origins=[],
        dev_users_json=json.dumps(TEST_USERS),
        rate_limit_capacity=30,
        rate_limit_refill_per_second=0.5,
        langsmith_tracing=False,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def login(client: TestClient):
    def _login(username: str = "viewer") -> dict[str, str]:
        response = client.post(
            "/api/v1/auth/token",
            json={"username": username,
                  "password": TEST_USERS[username]["password"]},
        )
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login
