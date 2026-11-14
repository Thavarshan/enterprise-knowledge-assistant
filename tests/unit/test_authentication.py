"""Verify signed token expiry, claims, and cross-instance validation.

All test identities and keys are synthetic and remain local to this module.
"""

import base64
import json
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from enterprise_assistant.api.application import create_app
from enterprise_assistant.config.settings import Settings
from enterprise_assistant.security.authentication import (
    AuthService,
    InvalidCredentialsError,
)
from enterprise_assistant.security.authorization import Role

USERS = {
    "analyst": {"password": "analyst-password", "role": "analyst"},
}
SIGNING_KEY = "test-signing-key-with-at-least-32-characters"


def service(
    *,
    secret: str = SIGNING_KEY,
    lifetime: int = 900,
) -> AuthService:
    """Create an isolated signed-token service for test identities.

    Args:
        secret: HMAC signing key passed to the service.
        lifetime: Maximum token age in seconds.

    Returns:
        Authentication service using only a synthetic account.
    """
    return AuthService(
        json.dumps(USERS),
        signing_secret=secret,
        issuer="test-issuer",
        audience="test-audience",
        token_ttl_seconds=lifetime,
    )


def test_login_issues_server_assigned_role_and_rejects_bad_password() -> None:
    """Issue a signed identity from configured user data only.

    Invalid credentials must not produce an authenticated identity.
    """
    auth = service()
    issued = auth.issue_token("analyst", "analyst-password")
    identity = auth.resolve_token(issued.access_token)

    assert identity is not None
    assert identity.user_id == "analyst"
    assert identity.role is Role.ANALYST
    with pytest.raises(InvalidCredentialsError):
        auth.issue_token("analyst", "wrong-password")


def test_token_rejects_expiration_wrong_key_and_tampered_role() -> None:
    """Reject expired, wrongly signed, and changed role claims.

    The resolver returns no identity for every invalid token variant.
    """
    auth = service()
    token = auth.issue_token("analyst", "analyst-password").access_token
    assert service(
        secret="different-key-with-at-least-32-characters"
    ).resolve_token(token) is None

    header, payload, signature = token.split(".")
    padding = "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload + padding))
    claims["role"] = "administrator"
    altered_payload = base64.urlsafe_b64encode(
        json.dumps(claims, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    tampered = f"{header}.{altered_payload}.{signature}"
    assert auth.resolve_token(tampered) is None

    now = int(time.time())
    expired = jwt.encode(
        {
            "sub": "analyst",
            "role": "analyst",
            "iss": "test-issuer",
            "aud": "test-audience",
            "iat": now - 120,
            "nbf": now - 120,
            "exp": now - 1,
            "jti": "expired-token-id",
        },
        SIGNING_KEY,
        algorithm="HS256",
    )
    assert auth.resolve_token(expired) is None


def test_token_requires_expected_issuer_and_audience() -> None:
    """Reject a correctly signed token minted for another API.

    Issuer and audience bind tokens to the intended service.
    """
    auth = service()
    now = int(time.time())
    wrong_audience = jwt.encode(
        {
            "sub": "analyst",
            "role": "analyst",
            "iss": "test-issuer",
            "aud": "other-api",
            "iat": now,
            "nbf": now,
            "exp": now + 300,
            "jti": "wrong-audience-token",
        },
        SIGNING_KEY,
        algorithm="HS256",
    )
    assert auth.resolve_token(wrong_audience) is None


def test_signed_identity_is_valid_across_separate_api_instances(
    tmp_path,
) -> None:
    """Accept the same token in separate apps configured with one key.

    This models stateless authentication across application instances.
    """
    settings = Settings(
        _env_file=None,
        app_env="test",
        mock_mode=True,
        sqlite_path=str(tmp_path / "sessions.sqlite3"),
        cors_origins=[],
        dev_users_json=json.dumps(USERS),
        auth_signing_secret=SIGNING_KEY,
        auth_issuer="test-issuer",
        auth_audience="test-audience",
    )
    first_app = create_app(settings)
    second_app = create_app(settings)

    with TestClient(first_app) as first, TestClient(second_app) as second:
        response = first.post(
            "/api/v1/auth/token",
            json={"username": "analyst", "password": "analyst-password"},
        )
        token = response.json()["access_token"]
        identity = second.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert identity.json() == {"user_id": "analyst", "role": "analyst"}


def test_login_request_cannot_choose_role(client: TestClient) -> None:
    """Reject browser-supplied roles through the strict API request schema.

    Role assignment remains controlled by the configured user record.
    """
    response = client.post(
        "/api/v1/auth/token",
        json={
            "username": "analyst",
            "password": "analyst-test-password",
            "role": "administrator",
        },
    )

    assert response.status_code == 422
