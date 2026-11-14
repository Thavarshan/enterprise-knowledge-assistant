"""Small HTTP/SSE client; application behavior remains in the FastAPI backend."""

import json
from collections.abc import Iterator
from typing import Any, cast

import httpx


class AssistantApiClient:
    def __init__(self, base_url: str, token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def login(self, username: str, password: str) -> str:
        response = httpx.post(
            f"{self.base_url}/api/v1/auth/token",
            json={"username": username, "password": password},
            timeout=10,
        )
        response.raise_for_status()
        return str(response.json()["access_token"])

    def get_identity(self) -> dict[str, Any]:
        response = httpx.get(f"{self.base_url}/api/v1/me", headers=self.headers, timeout=10)
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def create_session(self, title: str = "Demo conversation") -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/api/v1/chat/sessions",
            headers=self.headers,
            json={"title": title},
            timeout=10,
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def get_session(self, session_id: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.base_url}/api/v1/chat/sessions/{session_id}",
            headers=self.headers,
            timeout=10,
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def stream_chat(self, session_id: str, message: str) -> Iterator[dict[str, Any]]:
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
