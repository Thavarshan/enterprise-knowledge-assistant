"""Load development users and manage process-local bearer tokens.

Credentials come from inline JSON or a configured JSON file and are validated
with Pydantic. Successful login creates an opaque token mapped to a
server-owned user and role. Tokens exist only in this process and disappear
on restart; this service is for local development, not production identity.
"""

import hmac
import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from enterprise_assistant.security.authorization import Role


class AuthenticationConfigurationError(RuntimeError):
    """Report missing or invalid development-user configuration.

    This exception is converted to HTTP 503 by the login route. It should
    not include serialized credentials or secret values.
    """


class InvalidCredentialsError(PermissionError):
    """Report an unsuccessful local development login.

    The same message is used for unknown usernames and wrong passwords so
    the route does not reveal which account names exist.
    """


class DevUserConfig(BaseModel):
    """Validate one local development account record.

    Extra JSON keys are rejected. Passwords are plaintext in the local
    development file, so that file must be excluded from version control and
    protected with restrictive filesystem permissions.

    Attributes:
        password: Development-only password compared during login.
        role: Server-assigned role returned after successful login.

    Security:
        Pydantic's default representation includes the password. Do not log
        or format this model instance.
    """
    model_config = ConfigDict(extra="forbid")

    password: str
    role: Role


@dataclass(frozen=True)
class AuthenticatedUser:
    """Carry identity and role resolved by the API process.

    This value is created from configured accounts after login and is the
    trusted source for route ownership and tool policy decisions.

    Attributes:
        user_id: Configured account identifier.
        role: Server-assigned authorization role.
    """
    user_id: str
    role: Role


@dataclass(frozen=True)
class IssuedToken:
    """Represent an opaque token returned by development login.

    Attributes:
        access_token: Random bearer secret retained in process memory.
        token_type: Authorization scheme returned to the client.

    Security:
        The dataclass representation includes the token; do not log it.
    """
    access_token: str
    token_type: str = "bearer"


class AuthService:
    """Authenticate local accounts and resolve process-local tokens.

    User JSON is loaded from an inline value or file at construction.
    Successful login maps a random token to the configured username and
    role. Tokens have no expiry, are not persisted, and disappear on process
    restart, so this is not a production identity provider.

    Security:
        Passwords are stored as plaintext in the local development file.
        The file is expected to be ignored by Git and created with restricted
        permissions by the bootstrap script.
    """

    def __init__(self, configured_users_json: str) -> None:
        """Load account records and initialize the token map.

        Inline JSON is selected when the setting begins with an object
        delimiter; otherwise the value is read as an expanded file path.

        Args:
            configured_users_json: Inline account JSON or path to its file.

        Raises:
            AuthenticationConfigurationError: JSON, schema, or file access
                is invalid.
        """
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
        """Validate a password and issue an opaque bearer token.

        Unknown usernames use a random comparison value so they follow the
        password comparison path. The resulting token is kept only in this
        process.

        Args:
            username: Configured account name.
            password: Candidate password.

        Returns:
            Random bearer token and its type.

        Raises:
            AuthenticationConfigurationError: No accounts are configured.
            InvalidCredentialsError: Username or password is incorrect.
        """
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
        """Resolve a bearer token from the in-memory map.

        Args:
            token: Opaque token presented by the client.

        Returns:
            Authenticated identity or None when the token is unknown.
        """
        return self._tokens.get(token)
