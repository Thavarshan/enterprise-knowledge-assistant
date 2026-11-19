"""Test the D1 adapter contract with an in-process HTTP transport.

The mock responses exercise remote validation without cloud resources.
"""

import httpx
import pytest

from enterprise_assistant.memory.d1 import (
    D1SessionStore,
    SessionStoreUnavailable,
)


@pytest.mark.asyncio
async def test_d1_store_sends_backend_credentials_and_owner_scope() -> None:
    """Validate D1 request shapes and response conversion.

    The mock Worker echoes API-compatible records without an external call.
    """
    requests: list[httpx.Request] = []
    session_id = "b75e4b83-4767-4c7b-9d84-2f159057abcb"

    def handle(request: httpx.Request) -> httpx.Response:
        """Return deterministic Worker records and capture request metadata.

        Args:
            request: Incoming request intercepted by the mock transport.

        Returns:
            JSON response matching the D1 Worker API.
        """
        requests.append(request)
        if request.url.path == "/v1/sessions" and request.method == "POST":
            return httpx.Response(
                201,
                json={
                    "session_id": session_id,
                    "owner_id": "analyst",
                    "title": "New conversation",
                    "created_at": "2026-11-15T00:00:00+00:00",
                },
            )
        if request.url.path.endswith("/messages"):
            return httpx.Response(
                200,
                json={
                    "messages": [
                        {
                            "message_id": 1,
                            "session_id": session_id,
                            "role": "user",
                            "content": "Question",
                            "created_at": "2026-11-15T00:00:00+00:00",
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "session_id": session_id,
                "owner_id": "analyst",
                "title": "New conversation",
                "created_at": "2026-11-15T00:00:00+00:00",
            },
        )

    client = httpx.AsyncClient(
        base_url="https://d1-gateway.example",
        transport=httpx.MockTransport(handle),
    )
    store = D1SessionStore(
        "https://d1-gateway.example",
        "service-token-not-for-the-ui-00000000",
        client=client,
    )

    created = await store.create_session("analyst", "New conversation")
    fetched = await store.get_session(session_id, "analyst")
    messages = await store.list_messages(session_id, "analyst")

    assert created.session_id == session_id
    assert fetched is not None and fetched.owner_id == "analyst"
    assert messages is not None and messages[0].content == "Question"
    assert all(
        request.headers["authorization"]
        == "Bearer service-token-not-for-the-ui-00000000"
        for request in requests
    )
    assert all(
        request.headers["x-owner-id"] == "analyst" for request in requests
    )
    await client.aclose()


@pytest.mark.asyncio
async def test_d1_store_maps_missing_owner_and_appends_messages() -> None:
    """Map inaccessible sessions to None and append responses safely.

    A write succeeds only when its returned session identity matches.
    """
    session_id = "b75e4b83-4767-4c7b-9d84-2f159057abcb"
    appends: list[bytes] = []

    def handle(request: httpx.Request) -> httpx.Response:
        """Return owner misses or one validated appended message.

        Args:
            request: Mocked D1 Worker request.

        Returns:
            404 for reads and a message row for appends.
        """
        if request.method == "GET":
            return httpx.Response(404, json={"error": "not_found"})
        appends.append(request.content)
        return httpx.Response(
            201,
            json={
                "message_id": 4,
                "session_id": session_id,
                "role": "assistant",
                "content": "Answer",
                "created_at": "2026-11-15T00:00:00+00:00",
            },
        )

    client = httpx.AsyncClient(
        base_url="https://d1-gateway.example",
        transport=httpx.MockTransport(handle),
    )
    store = D1SessionStore(
        "https://d1-gateway.example",
        "service-token-not-for-the-ui-00000000",
        client=client,
    )

    assert await store.get_session(session_id, "viewer") is None
    assert await store.list_messages(session_id, "viewer") is None
    message = await store.append_message(
        session_id,
        "analyst",
        "assistant",
        "Answer",
    )

    assert message.message_id == 4
    assert message.content == "Answer"
    assert b'"content":"Answer"' in appends[0]
    await client.aclose()


@pytest.mark.asyncio
async def test_d1_store_rejects_bad_payloads_and_worker_timeouts() -> None:
    """Translate malformed responses and network failures to safe errors.

    Readiness reports false while initialization raises a safe exception.
    """

    def invalid_response(_request: httpx.Request) -> httpx.Response:
        """Return a response missing required session identity fields.

        Args:
            _request: Mocked request; its values are not used.

        Returns:
            Malformed JSON response to exercise strict output validation.
        """
        return httpx.Response(200, json={"session_id": "bad"})

    client = httpx.AsyncClient(
        base_url="https://d1-gateway.example",
        transport=httpx.MockTransport(invalid_response),
    )
    store = D1SessionStore(
        "https://d1-gateway.example",
        "service-token-not-for-the-ui-00000000",
        client=client,
    )
    with pytest.raises(SessionStoreUnavailable):
        await store.create_session("analyst")
    await client.aclose()

    def timeout(_request: httpx.Request) -> httpx.Response:
        """Raise an HTTP timeout without contacting a network service.

        Args:
            _request: Mock request that would have been sent to the Worker.

        Raises:
            httpx.ReadTimeout: Simulated Worker timeout.
        """
        raise httpx.ReadTimeout("synthetic timeout")

    timeout_client = httpx.AsyncClient(
        base_url="https://d1-gateway.example",
        transport=httpx.MockTransport(timeout),
    )
    timeout_store = D1SessionStore(
        "https://d1-gateway.example",
        "service-token-not-for-the-ui-00000000",
        client=timeout_client,
    )
    assert not await timeout_store.healthcheck()
    with pytest.raises(SessionStoreUnavailable):
        await timeout_store.initialize()
    await timeout_client.aclose()


@pytest.mark.asyncio
async def test_d1_store_rejects_mismatched_owner_and_does_not_retry() -> None:
    """Reject cross-owner responses and never replay ambiguous writes.

    A timeout after a write remains an error instead of triggering a retry.
    """
    calls = 0

    def mismatched_owner(_request: httpx.Request) -> httpx.Response:
        """Return an otherwise valid session for a different owner.

        Args:
            _request: Mocked request whose values are not needed.

        Returns:
            Structurally valid record with an unexpected owner.
        """
        return httpx.Response(
            200,
            json={
                "session_id": "b75e4b83-4767-4c7b-9d84-2f159057abcb",
                "owner_id": "viewer",
                "title": "New conversation",
                "created_at": "2026-11-15T00:00:00+00:00",
            },
        )

    client = httpx.AsyncClient(
        base_url="https://d1-gateway.example",
        transport=httpx.MockTransport(mismatched_owner),
    )
    store = D1SessionStore(
        "https://d1-gateway.example",
        "service-token-not-for-the-ui-00000000",
        client=client,
    )
    with pytest.raises(SessionStoreUnavailable):
        await store.create_session("analyst")
    await client.aclose()

    def ambiguous_timeout(_request: httpx.Request) -> httpx.Response:
        """Raise a synthetic timeout after one attempted message append.

        Args:
            _request: Single mocked write request.

        Raises:
            httpx.ReadTimeout: Simulated ambiguous remote completion.
        """
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("synthetic timeout")

    timeout_client = httpx.AsyncClient(
        base_url="https://d1-gateway.example",
        transport=httpx.MockTransport(ambiguous_timeout),
    )
    timeout_store = D1SessionStore(
        "https://d1-gateway.example",
        "service-token-not-for-the-ui-00000000",
        client=timeout_client,
    )
    with pytest.raises(SessionStoreUnavailable):
        await timeout_store.append_message(
            "b75e4b83-4767-4c7b-9d84-2f159057abcb",
            "analyst",
            "user",
            "Question",
        )
    assert calls == 1
    await timeout_client.aclose()
