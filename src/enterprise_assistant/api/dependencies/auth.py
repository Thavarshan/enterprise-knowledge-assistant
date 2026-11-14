"""Bearer identity dependency; user and role are resolved by the API process."""

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
