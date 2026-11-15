"""Provide the synchronous HTTP and SSE client used by Streamlit.

The client owns request URLs, bearer headers, timeouts, and SSE line
parsing. Streamlit calls are synchronous, which keeps UI code straightforward
but occupies the UI worker while a chat response is being consumed.
"""

import json
from collections.abc import Iterator
from typing import Any, cast

import httpx


class AssistantApiClient:
    """Call the FastAPI service from the synchronous Streamlit UI.

    The wrapper centralizes the base URL, bearer header, request timeouts,
    and SSE data-line parsing. Calls use module-level httpx functions and
    are blocking while network I/O completes.

    Attributes:
        base_url: API origin without a trailing slash.
        token: Optional bearer token for protected routes.
    """

    def __init__(self, base_url: str, token: str | None = None) -> None:
        """Store the API origin and optional bearer token.

        Args:
            base_url: Base HTTP URL for the API.
            token: Token obtained from the login endpoint, if signed in.
        """
        self.base_url = base_url.rstrip("/")
        self.token = token

    @property
    def headers(self) -> dict[str, str]:
        """Build the bearer authorization header when signed in.

        Returns:
            Authorization header mapping, or an empty mapping without a
            token.
        """
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def login(self, username: str, password: str) -> str:
        """Exchange development credentials for a bearer token.

        Args:
            username: Configured development account name.
            password: Account password entered in the UI.

        Returns:
            Signed bearer token from the API response.

        Raises:
            httpx.HTTPError: The API request fails or returns an error.
        """
        response = httpx.post(
            f"{self.base_url}/api/v1/auth/token",
            json={"username": username, "password": password},
            timeout=10,
        )
        response.raise_for_status()
        return str(response.json()["access_token"])

    def get_identity(self) -> dict[str, Any]:
        """Fetch the identity associated with this client's token.

        Returns:
            JSON identity payload containing user ID and role.

        Raises:
            httpx.HTTPError: The API request fails or is unauthorized.
        """
        response = httpx.get(f"{self.base_url}/api/v1/me",
                             headers=self.headers, timeout=10)
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def get_version(self) -> dict[str, str]:
        """Fetch the active model and retrieval configuration.

        Returns:
            Public provider, model, retrieval, mode, and release metadata.

        Raises:
            httpx.HTTPError: The API request fails or returns an error.
        """
        response = httpx.get(f"{self.base_url}/version", timeout=5)
        response.raise_for_status()
        return cast(dict[str, str], response.json())

    def create_session(
        self, title: str = "Demo conversation"
    ) -> dict[str, Any]:
        """Create a new conversation through the API.

        Args:
            title: Display title to send with the request.

        Returns:
            JSON session response.

        Raises:
            httpx.HTTPError: The API request fails.
        """
        response = httpx.post(
            f"{self.base_url}/api/v1/chat/sessions",
            headers=self.headers,
            json={"title": title},
            timeout=10,
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def get_session(self, session_id: str) -> dict[str, Any]:
        """Fetch a session and its persisted message history.

        Args:
            session_id: Owner-scoped session ID to retrieve.

        Returns:
            JSON session detail payload.

        Raises:
            httpx.HTTPError: The API request fails or the session is absent.
        """
        response = httpx.get(
            f"{self.base_url}/api/v1/chat/sessions/{session_id}",
            headers=self.headers,
            timeout=10,
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def stream_chat(
        self, session_id: str, message: str
    ) -> Iterator[dict[str, Any]]:
        """Post a user turn and parse SSE data records.

        The method keeps the streaming response open while iterating lines.
        It parses data fields as JSON and yields each event payload; it does
        not assemble multi-line SSE data fields.

        Args:
            session_id: Existing conversation session.
            message: User text submitted for the current turn.

        Yields:
            Parsed JSON objects from non-empty data lines.

        Raises:
            httpx.HTTPError: The request fails or returns an error status.
            json.JSONDecodeError: An event data line is not valid JSON.

        Concurrency:
            This iterator performs blocking HTTP I/O on the Streamlit
            execution thread.
        """
        with httpx.stream(
            "POST",
            f"{self.base_url}/api/v1/chat/stream",
            headers=self.headers,
            json={"session_id": session_id, "message": message},
            timeout=60,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith("data:"):
                    raw = line.removeprefix("data:").strip()
                    if raw:
                        yield json.loads(raw)
