"""FastAPI authentication, session isolation, and event streaming tests."""

from collections.abc import Callable

from fastapi.testclient import TestClient


def test_health_readiness_and_bearer_identity(client: TestClient, login: Callable) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}
    assert client.get("/api/v1/me").status_code == 401

    headers = login("analyst")
    response = client.get("/api/v1/me", headers=headers)
    assert response.json() == {"user_id": "analyst", "role": "analyst"}


def test_chat_session_is_owned_and_messages_survive_turns(
    client: TestClient, login: Callable
) -> None:
    viewer_headers = login("viewer")
    analyst_headers = login("analyst")
    session = client.post(
        "/api/v1/chat/sessions", headers=viewer_headers, json={"title": "Payments"}
    )
    assert session.status_code == 201
    session_id = session.json()["session_id"]

    assert (
        client.get(f"/api/v1/chat/sessions/{session_id}", headers=analyst_headers).status_code
        == 404
    )
    for question in ("What does the gateway timeout runbook say?", "How do payment retries work?"):
        streamed = client.post(
            "/api/v1/chat/stream",
            headers=viewer_headers,
            json={"session_id": session_id, "message": question},
        )
        assert streamed.status_code == 200
        assert "event: completed" in streamed.text

    detail = client.get(f"/api/v1/chat/sessions/{session_id}", headers=viewer_headers).json()
    assert [message["role"] for message in detail["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert "doc-runbook-gateway-timeout-001" in detail["messages"][1]["content"]


def test_stream_contains_actual_graph_activity_and_request_id(
    client: TestClient, login: Callable
) -> None:
    headers = login()
    session_id = client.post("/api/v1/chat/sessions", headers=headers, json={}).json()["session_id"]
    response = client.post(
        "/api/v1/chat/stream",
        headers={**headers, "X-Request-ID": "assessment-request-42"},
        json={"session_id": session_id, "message": "Investigate the payment timeout incident"},
    )
    assert response.headers["x-request-id"] == "assessment-request-42"
    assert "event: agent_transition" in response.text
    assert "event: tool_execution" in response.text
    assert "event: retrieval" in response.text
    assert "event: response_chunk" in response.text
    assert "event: validation" in response.text
    assert "event: memory_update" in response.text
    assert "event: completed" in response.text
    assert '"node":"research"' in response.text
    assert response.text.index("event: validation") < response.text.index("event: response_chunk")


def test_stream_rejects_unauthenticated_and_invalid_body(
    client: TestClient, login: Callable
) -> None:
    assert (
        client.post(
            "/api/v1/chat/stream", json={"session_id": "x", "message": "question"}
        ).status_code
        == 401
    )
    invalid = client.post(
        "/api/v1/chat/stream",
        headers=login(),
        json={"session_id": "x", "message": "   "},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
