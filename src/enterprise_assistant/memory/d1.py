"""Persist conversation data through the dedicated Cloudflare D1 Worker.

This adapter only calls the application's narrow Worker API. It never uses
Cloudflare's administrative database API or sends credentials to the UI.
"""

from typing import Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from enterprise_assistant.memory.models import (
    ChatMessage,
    ChatSession,
    MessageRole,
)


class SessionStoreUnavailable(RuntimeError):
    """Report an unavailable or invalid remote session store response.

    The message remains safe to return to API callers without exposing
    credentials or provider details.
    """


class _SessionPayload(BaseModel):
    """Validate a session record returned by the Worker.

    Strict validation rejects unexpected fields and coerced values.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    session_id: str = Field(min_length=1, max_length=80)
    owner_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=120)
    created_at: str = Field(min_length=1, max_length=40)


class _SessionListPayload(BaseModel):
    """Validate a bounded list of owner-scoped session records.

    Worker responses may contain at most one hundred session records.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    sessions: list[_SessionPayload] = Field(max_length=100)


class _MessagePayload(BaseModel):
    """Validate a message record returned by the Worker.

    The field bounds keep a remote response from growing without limit.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    message_id: int = Field(gt=0)
    session_id: str = Field(min_length=1, max_length=80)
    role: Literal["user", "assistant"]
    content: str = Field(max_length=40_000)
    created_at: str = Field(min_length=1, max_length=40)


class _MessageListPayload(BaseModel):
    """Validate a bounded message history response.

    Worker responses may contain at most one thousand history records.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    messages: list[_MessagePayload] = Field(max_length=1000)


class D1SessionStore:
    """Implement owner-scoped storage with a reusable async HTTP client.

    Attributes:
        api_url: Base URL of the dedicated authenticated D1 Worker.
        _client: Reusable asynchronous HTTP connection pool.

    The API token and owner ID are sent only from this backend adapter. Calls
    are not retried automatically so an ambiguous append is never replayed.
    """

    def __init__(
        self,
        api_url: str,
        service_token: str,
        timeout_seconds: int = 5,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Create a D1 adapter and configure request timeouts.

        Args:
            api_url: Base URL of the deployment's Worker endpoint.
            service_token: Backend-only credential provisioned as a Worker
                secret.
            timeout_seconds: Total request timeout; connect time is capped
                at three seconds.
            client: Optional injected client for deterministic tests.
        """
        self.api_url = api_url.rstrip("/")
        self._service_token = service_token
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.api_url,
            timeout=httpx.Timeout(
                timeout_seconds,
                connect=min(timeout_seconds, 3),
            ),
            headers={
                "Authorization": f"Bearer {service_token}",
                "Accept": "application/json",
            },
        )

    async def aclose(self) -> None:
        """Close the HTTP connection pool during application shutdown.

        Injected clients stay owned by their caller and are left open.
        """
        if self._owns_client:
            await self._client.aclose()

    async def initialize(self) -> None:
        """Check Worker credentials and local or remote schema readiness.

        Raises:
            SessionStoreUnavailable: The Worker or D1 binding is unavailable.
        """
        try:
            response = await self._request("GET", "/internal/ready")
            if response is None:
                raise SessionStoreUnavailable(
                    "Configured session store is not ready."
                )
            if response.json() != {"status": "ready"}:
                raise SessionStoreUnavailable(
                    "Configured session store is not ready."
                )
        except (httpx.HTTPError, ValueError) as exc:
            raise SessionStoreUnavailable(
                "Configured session store is not ready."
            ) from exc

    async def healthcheck(self) -> bool:
        """Return whether the authenticated Worker readiness check passes.

        Network and response errors become a false health result.
        """
        try:
            response = await self._request("GET", "/internal/ready")
            return response is not None and response.json() == {
                "status": "ready",
            }
        except (httpx.HTTPError, SessionStoreUnavailable, ValueError):
            return False

    async def create_session(
        self, owner_id: str, title: str | None = None
    ) -> ChatSession:
        """Create a session through the owner-scoped Worker endpoint.

        Args:
            owner_id: User identifier resolved from a verified API token.
            title: Optional session title.

        Returns:
            Newly created conversation.

        Raises:
            SessionStoreUnavailable: The Worker fails or returns invalid data.
        """
        response = await self._request(
            "POST",
            "/v1/sessions",
            owner_id=owner_id,
            json={"title": title},
        )
        if response is None:
            raise SessionStoreUnavailable(
                "Session store returned an invalid session response."
            )
        session = self._session_from_response(response)
        if session.owner_id != owner_id:
            raise SessionStoreUnavailable(
                "Session store returned an invalid session response."
            )
        return session

    async def list_sessions(self, owner_id: str) -> list[ChatSession]:
        """List sessions returned by the owner-scoped Worker endpoint.

        Args:
            owner_id: Authenticated account identifier.

        Returns:
            Up to 100 validated sessions ordered newest first.

        Raises:
            SessionStoreUnavailable: The Worker fails or returns invalid data.
        """
        response = await self._request(
            "GET",
            "/v1/sessions",
            owner_id=owner_id,
        )
        if response is None:
            raise SessionStoreUnavailable(
                "Session store returned an invalid session list."
            )
        try:
            payload = _SessionListPayload.model_validate(response.json())
        except (ValidationError, ValueError) as exc:
            raise SessionStoreUnavailable(
                "Session store returned an invalid session list."
            ) from exc
        sessions = [
            ChatSession(**session.model_dump())
            for session in payload.sessions
        ]
        if any(session.owner_id != owner_id for session in sessions):
            raise SessionStoreUnavailable(
                "Session store returned an invalid session list."
            )
        return sessions

    async def get_session(
        self, session_id: str, owner_id: str
    ) -> ChatSession | None:
        """Fetch a session only when its owner matches.

        Args:
            session_id: Session identifier to locate.
            owner_id: Authenticated owner identifier.

        Returns:
            The session, or None when absent or owned by another user.
        """
        response = await self._request(
            "GET",
            f"/v1/sessions/{quote(session_id, safe='')}",
            owner_id=owner_id,
            missing_ok=True,
        )
        if response is None:
            return None
        session = self._session_from_response(response)
        if session.session_id != session_id or session.owner_id != owner_id:
            raise SessionStoreUnavailable(
                "Session store returned an invalid session response."
            )
        return session

    async def list_messages(
        self, session_id: str, owner_id: str
    ) -> list[ChatMessage] | None:
        """Read ordered history after Worker-side ownership validation.

        Args:
            session_id: Session identifier to read.
            owner_id: Authenticated owner identifier.

        Returns:
            Up to 1000 latest messages in ascending order, or None when
            the session is absent or owned by another user.
        """
        response = await self._request(
            "GET",
            f"/v1/sessions/{quote(session_id, safe='')}/messages",
            owner_id=owner_id,
            missing_ok=True,
        )
        if response is None:
            return None
        try:
            payload = _MessageListPayload.model_validate(response.json())
        except (ValidationError, ValueError) as exc:
            raise SessionStoreUnavailable(
                "Session store returned an invalid history response."
            ) from exc
        messages = [
            ChatMessage(**message.model_dump())
            for message in payload.messages
        ]
        if any(message.session_id != session_id for message in messages):
            raise SessionStoreUnavailable(
                "Session store returned an invalid history response."
            )
        return messages

    async def append_message(
        self,
        session_id: str,
        owner_id: str,
        role: MessageRole,
        content: str,
    ) -> ChatMessage:
        """Append a message only after the Worker verifies ownership.

        Args:
            session_id: Destination session identifier.
            owner_id: Authenticated owner identifier.
            role: User or assistant message role.
            content: Message text to persist.

        Returns:
            Persisted message record.

        Raises:
            LookupError: The session does not exist for this owner.
            SessionStoreUnavailable: The Worker fails or returns invalid data.
        """
        response = await self._request(
            "POST",
            f"/v1/sessions/{quote(session_id, safe='')}/messages",
            owner_id=owner_id,
            json={"role": role, "content": content},
            missing_ok=True,
        )
        if response is None:
            raise LookupError("Session does not exist for this user.")
        try:
            message = _MessagePayload.model_validate(response.json())
        except (ValidationError, ValueError) as exc:
            raise SessionStoreUnavailable(
                "Session store returned an invalid message response."
            ) from exc
        if (
            message.session_id != session_id
            or message.role != role
            or message.content != content
        ):
            raise SessionStoreUnavailable(
                "Session store returned an invalid message response."
            )
        return ChatMessage(**message.model_dump())

    async def _request(
        self,
        method: str,
        path: str,
        *,
        owner_id: str | None = None,
        missing_ok: bool = False,
        json: dict[str, str | None] | None = None,
    ) -> httpx.Response | None:
        """Send a backend-authenticated request without leaking details.

        Args:
            method: HTTP method for the narrow Worker route.
            path: Relative route path.
            owner_id: Verified owner identifier, when the route is scoped.
            missing_ok: Convert HTTP 404 to a missing record.
            json: Optional JSON body for the JSON-only Worker endpoints.

        Returns:
            Successful response, or None for an allowed 404.

        Raises:
            SessionStoreUnavailable: Network, authorization, server, or
                response errors occur.
        """
        headers = {"Authorization": f"Bearer {self._service_token}"}
        if owner_id:
            headers["X-Owner-ID"] = owner_id
        try:
            response = await self._client.request(
                method,
                path,
                headers=headers,
                json=json,
            )
        except httpx.HTTPError as exc:
            raise SessionStoreUnavailable(
                "Configured session store could not be reached."
            ) from exc
        if missing_ok and response.status_code == 404:
            return None
        if not response.is_success:
            raise SessionStoreUnavailable(
                "Configured session store request failed."
            )
        return response

    @staticmethod
    def _session_from_response(
        response: httpx.Response,
    ) -> ChatSession:
        """Validate a Worker response and convert it to the domain record.

        Args:
            response: Successful HTTP response from the D1 Worker.

        Returns:
            Validated adapter-neutral session.

        Raises:
            SessionStoreUnavailable: The response does not match the schema.
        """
        try:
            payload = _SessionPayload.model_validate(response.json())
        except (ValidationError, ValueError) as exc:
            raise SessionStoreUnavailable(
                "Session store returned an invalid session response."
            ) from exc
        return ChatSession(**payload.model_dump())
