"""Development authentication with server-owned user roles and opaque tokens."""

import hmac
import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from enterprise_assistant.security.authorization import Role


class AuthenticationConfigurationError(RuntimeError):
    """Raised when local development credentials are absent or malformed."""


class InvalidCredentialsError(PermissionError):
    """Raised for an unknown user or incorrect password."""


class DevUserConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str
    role: Role


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    role: Role


@dataclass(frozen=True)
class IssuedToken:
    access_token: str
    token_type: str = "bearer"


class AuthService:
    """A process-local token store intended only for development and tests."""

    def __init__(self, configured_users_json: str) -> None:
        self._tokens: dict[str, AuthenticatedUser] = {}
        configured_value = configured_users_json.strip()
        if not configured_value:
            self._users: dict[str, DevUserConfig] = {}
            return
        try:
            if configured_value.startswith("{"):
                raw_users: Any = json.loads(configured_value)
            else:
                users_path = Path(configured_value).expanduser()
                raw_users = json.loads(
                    users_path.read_text(encoding="utf-8")
                )
            if not isinstance(raw_users, dict) or not raw_users:
                raise ValueError("expected a non-empty JSON object")
            self._users = {
                username: DevUserConfig.model_validate(user)
                for username, user in raw_users.items()
            }
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise AuthenticationConfigurationError(
                "DEV_USERS_JSON must contain user JSON or point to a JSON file."
            ) from exc
        except OSError as exc:
            raise AuthenticationConfigurationError(
                "DEV_USERS_JSON must point to a readable JSON file."
            ) from exc

    def issue_token(self, username: str, password: str) -> IssuedToken:
        if not self._users:
            raise AuthenticationConfigurationError(
                "No development accounts configured. "
                "Run `make setup` to create .env."
            )
        account = self._users.get(username)
        expected_password = (
            account.password
            if account is not None
            else secrets.token_urlsafe(24)
        )
        if account is None or not hmac.compare_digest(
            password, expected_password
        ):
            raise InvalidCredentialsError("Invalid username or password.")
        token = secrets.token_urlsafe(32)
        self._tokens[token] = AuthenticatedUser(
            user_id=username, role=account.role)
        return IssuedToken(access_token=token)

    def resolve_token(self, token: str) -> AuthenticatedUser | None:
        return self._tokens.get(token)
