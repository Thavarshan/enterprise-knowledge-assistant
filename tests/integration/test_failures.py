"""Verify graph dependency failures become safe user-visible events.

A failing retriever simulates provider outage. The test checks that exception
text is withheld and that no assistant answer is persisted after graph
failure.
"""

import json
from datetime import date

from fastapi.testclient import TestClient

from enterprise_assistant.api.application import create_app
from enterprise_assistant.config.settings import Settings
from enterprise_assistant.domain.models import SearchResult
from enterprise_assistant.retrieval.interfaces import Retriever


class FailingRetriever:
    """Simulate a provider failure through the Retriever contract.

    The adapter raises a synthetic runtime error so tests can verify the
    graph boundary returns a generic failure and does not save an assistant
    answer.
    """

    async def search(
        self,
        query: str,
        *,
        allowed_access_levels: frozenset[str],
        department: str | None = None,
        document_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Raise a deterministic provider error for every query.

        Args:
            query: Search text, unused in this failure adapter.
            allowed_access_levels: Access labels, unused in this adapter.
            department: Optional filter, unused in this adapter.
            document_type: Optional type filter, unused in this adapter.
            date_from: Optional lower date, unused in this adapter.
            date_to: Optional upper date, unused in this adapter.
            limit: Result cap, unused in this adapter.

        Raises:
            RuntimeError: Always, to simulate an unavailable provider.
        """
        del (
            query,
            allowed_access_levels,
            department,
            document_type,
            date_from,
            date_to,
            limit,
        )
        raise RuntimeError("synthetic provider outage")


def test_retrieval_failure_is_streamed_without_exception_details(
    tmp_path,
) -> None:
    """Verify provider details stay server-side on graph failure.

    The user message is already stored before graph execution; the
    assistant answer is not persisted when retrieval fails.

    Args:
        tmp_path: Pytest-managed directory for the temporary database.
    """
    settings = Settings(
        _env_file=None,
        app_env="test",
        sqlite_path=str(tmp_path / "failed.sqlite3"),
        cors_origins=[],
        dev_users_json=json.dumps(
            {"viewer": {"password": "pw", "role": "viewer"}}
        ),
    )
    failing_retriever: Retriever = FailingRetriever()
    with TestClient(
        create_app(settings, retriever=failing_retriever)
    ) as client:
        token = client.post(
            "/api/v1/auth/token", json={"username": "viewer", "password": "pw"}
        )
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
        assert "event: tool_start" in response.text
        assert "knowledge_search_failed" in response.text
        assert response.text.index("event: tool_start") < response.text.index(
            "knowledge_search_failed"
        )
        detail = client.get(
            f"/api/v1/chat/sessions/{session_id}", headers=headers
        ).json()
        assert [message["role"] for message in detail["messages"]] == ["user"]
