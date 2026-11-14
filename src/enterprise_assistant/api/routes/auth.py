"""Expose local development login and identity routes.

The token route delegates credential checks to `AuthService` and maps
invalid credentials or missing configuration to safe HTTP errors. The
identity route returns the user and role resolved by the bearer dependency.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from enterprise_assistant.api.dependencies.auth import get_current_user
from enterprise_assistant.api.schemas.auth import (
    TokenRequest,
    TokenResponse,
    UserResponse,
)
from enterprise_assistant.security.authentication import (
    AuthenticatedUser,
    AuthenticationConfigurationError,
    InvalidCredentialsError,
)

router = APIRouter(tags=["authentication"])


@router.post("/auth/token", response_model=TokenResponse)
async def issue_token(payload: TokenRequest, request: Request) -> TokenResponse:
    """Authenticate a configured development user and issue a bearer token.

    The route maps invalid credentials to 401 and missing or malformed
    development-user configuration to 503. The token and role are
    produced by the backend; the request cannot supply a role.

    Args:
        payload: Validated username and password.
        request: Request used to access the application AuthService.

    Returns:
        Bearer token response.

    Raises:
        HTTPException: 401 for bad credentials or 503 when accounts are
            not configured.
    """
    auth = request.app.state.container.auth
    try:
        token = auth.issue_token(payload.username, payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except AuthenticationConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return TokenResponse(
        access_token=token.access_token,
        token_type=token.token_type,
        expires_in=token.expires_in,
    )


@router.get("/me", response_model=UserResponse)
async def current_identity(
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
) -> UserResponse:
    """Return the identity resolved from the bearer token.

    This endpoint reports the server-assigned role and does not accept
    identity attributes from the request body.

    Args:
        user: Authenticated user supplied by the bearer dependency.

    Returns:
        User ID and role from the token store.
    """
    return UserResponse(user_id=user.user_id, role=user.role)
