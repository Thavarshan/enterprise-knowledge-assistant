"""Resolve a bearer token to the API process's authenticated user.

FastAPI routes depend on this function before reading sessions or starting
chat. The token store returns the user and role established at login; missing
or unknown tokens are rejected with an HTTP 401 challenge.
"""

from typing import cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from enterprise_assistant.security.authentication import AuthenticatedUser

_bearer = HTTPBearer(auto_error=False)
_bearer_dependency = Depends(_bearer)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = (
        _bearer_dependency
    ),
) -> AuthenticatedUser:
    """Resolve the bearer credentials to server-owned identity.

    FastAPI uses this dependency on protected routes. It looks up the token
    in the process-local AuthService, so a client cannot choose its role by
    submitting a role field.

    Args:
        request: Current request with the application service container.
        credentials: Optional parsed HTTP bearer credentials.

    Returns:
        The user and role established when the token was issued.

    Raises:
        HTTPException: With 401 and a Bearer challenge when credentials are
            missing or unknown.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = cast(
        AuthenticatedUser | None,
        request.app.state.container.auth.resolve_token(
            credentials.credentials),
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
