"""Authenticate configured demo users and issue signed bearer tokens.

Passwords are loaded from an ignored local file or server-only inline JSON.
Signed tokens carry the configured account's identity and role, allowing
independent API instances with the same secret to authenticate a request.
"""

import hmac
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt
from pydantic import BaseModel, ConfigDict, ValidationError

from enterprise_assistant.security.authorization import Role


class AuthenticationConfigurationError(RuntimeError):
    """Report missing or invalid configured account information.

    This error prevents the service from starting with unsafe credentials.
    """


class InvalidCredentialsError(PermissionError):
    """Report an unsuccessful login without revealing account existence.

    Callers use one error for unknown users and incorrect passwords.
    """


class DevUserConfig(BaseModel):
    """Validate a configured development account record.

    Attributes:
        password: Password checked at login and never included in logs.
        role: Server-assigned role included in the signed token.
    """

    model_config = ConfigDict(extra="forbid")

    password: str
    role: Role


@dataclass(frozen=True)
class AuthenticatedUser:
    """Carry identity claims verified by the backend.

    Attributes:
        user_id: Configured account identifier from the signed subject.
        role: Server-assigned authorization role from the signed token.
    """

    user_id: str
    role: Role


@dataclass(frozen=True)
class IssuedToken:
    """Represent the bearer token returned after successful login.

    Attributes:
        access_token: Signed bearer credential; do not log this value.
        token_type: Authorization scheme, normally ``bearer``.
        expires_in: Token lifetime in seconds.
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 900


class AuthService:
    """Verify demo passwords and sign short-lived stateless tokens.

    Production deployments must supply a high-entropy signing key. Local
    development creates an ephemeral key only when none is configured;
    tokens then intentionally stop working after that process restarts.

    Attributes:
        issuer: Required token issuer claim.
        audience: Required token audience claim.
        token_ttl_seconds: Maximum signed-token lifetime.
    """

    def __init__(
        self,
        configured_users_json: str,
        *,
        signing_secret: str | None = None,
        issuer: str = "viridian",
        audience: str = "viridian-api",
        token_ttl_seconds: int = 900,
    ) -> None:
        """Load account configuration and token verification settings.

        Args:
            configured_users_json: Inline JSON or path to a local JSON file.
            signing_secret: Shared HMAC key; a random process-local key is
                generated only outside production when omitted.
            issuer: Expected issuer claim.
            audience: Expected audience claim.
            token_ttl_seconds: Signed-token lifetime in seconds.

        Raises:
            AuthenticationConfigurationError: Account JSON is invalid.
            ValueError: The key is too short or token lifetime is invalid.
        """
        if token_ttl_seconds < 60 or token_ttl_seconds > 86_400:
            raise ValueError("Token lifetime must be between 60 and 86400.")
        if signing_secret and len(signing_secret) < 32:
            raise ValueError("Signing secret must contain 32 characters.")
        self._signing_secret = signing_secret or secrets.token_urlsafe(48)
        self.issuer = issuer
        self.audience = audience
        self.token_ttl_seconds = token_ttl_seconds
        configured_value = configured_users_json.strip()
        if not configured_value:
            self._users: dict[str, DevUserConfig] = {}
            return
        try:
            if configured_value.startswith("{"):
                raw_users: Any = json.loads(configured_value)
            else:
                users_path = Path(configured_value).expanduser()
                raw_users = json.loads(users_path.read_text(encoding="utf-8"))
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
        """Verify a configured password and sign a short-lived JWT.

        Args:
            username: Configured account name.
            password: Candidate password.

        Returns:
            Signed bearer token and its token type.

        Raises:
            AuthenticationConfigurationError: No accounts are configured.
            InvalidCredentialsError: Username or password is incorrect.
        """
        if not self._users:
            raise AuthenticationConfigurationError(
                "No development accounts configured. "
                "Run `make setup` to create local accounts."
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
        now = int(time.time())
        token = jwt.encode(
            {
                "sub": username,
                "role": account.role.value,
                "iss": self.issuer,
                "aud": self.audience,
                "iat": now,
                "nbf": now,
                "exp": now + self.token_ttl_seconds,
                "jti": secrets.token_urlsafe(18),
            },
            self._signing_secret,
            algorithm="HS256",
        )
        return IssuedToken(
            access_token=token,
            expires_in=self.token_ttl_seconds,
        )

    def resolve_token(self, token: str) -> AuthenticatedUser | None:
        """Verify token signature and claims before returning its identity.

        Args:
            token: Bearer token supplied by the HTTP client.

        Returns:
            Verified user identity, or None for invalid or expired tokens.
        """
        try:
            claims = jwt.decode(
                token,
                self._signing_secret,
                algorithms=["HS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={
                    "require": [
                        "sub",
                        "role",
                        "iss",
                        "aud",
                        "iat",
                        "nbf",
                        "exp",
                        "jti",
                    ]
                },
            )
            subject = claims.get("sub")
            if not isinstance(subject, str) or not subject:
                return None
            role_claim = claims.get("role")
            if not isinstance(role_claim, str):
                return None
            return AuthenticatedUser(
                user_id=subject,
                role=Role(role_claim),
            )
        except (jwt.InvalidTokenError, ValueError, TypeError):
            return None
