"""Graceful graph dependency failure behavior."""

import json

from fastapi.testclient import TestClient

from enterprise_assistant.api.application import create_app
from enterprise_assistant.config.settings import Settings
from enterprise_assistant.domain.models import SearchResult
from enterprise_assistant.retrieval.interfaces import Retriever


class FailingRetriever:
    async def search(
        self,
        query: str,
        *,
        allowed_access_levels: frozenset[str],
        department: str | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        del query, allowed_access_levels, department, limit
        raise RuntimeError("synthetic provider outage")


def test_retrieval_failure_is_streamed_without_exception_details(
    tmp_path,
) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        sqlite_path=str(tmp_path / "failed.sqlite3"),
        cors_origins=[],
        dev_users_json=json.dumps(
            {"viewer": {"password": "pw", "role": "viewer"}}),
    )
    failing_retriever: Retriever = FailingRetriever()
    with TestClient(
        create_app(settings, retriever=failing_retriever)
    ) as client:
        token = client.post("/api/v1/auth/token",
                            json={"username": "viewer", "password": "pw"})
        headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
        session_id = client.post(
            "/api/v1/chat/sessions", headers=headers, json={}
        ).json()["session_id"]
        response = client.post(
            "/api/v1/chat/stream",
            headers=headers,
            json={"session_id": session_id, "message": "payment timeout"},
        )
        assert "event: failure" in response.text
        assert "synthetic provider outage" not in response.text
        detail = client.get(
            f"/api/v1/chat/sessions/{session_id}", headers=headers).json()
        assert [message["role"] for message in detail["messages"]] == ["user"]
