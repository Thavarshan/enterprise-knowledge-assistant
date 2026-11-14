"""Local development token endpoint and authenticated identity lookup."""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from enterprise_assistant.api.dependencies.auth import get_current_user
from enterprise_assistant.api.schemas.auth import TokenRequest, TokenResponse, UserResponse
from enterprise_assistant.security.authentication import (
    AuthenticatedUser,
    AuthenticationConfigurationError,
    InvalidCredentialsError,
)

router = APIRouter(tags=["authentication"])


@router.post("/auth/token", response_model=TokenResponse)
async def issue_token(payload: TokenRequest, request: Request) -> TokenResponse:
    auth = request.app.state.container.auth
    try:
        token = auth.issue_token(payload.username, payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except AuthenticationConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return TokenResponse(access_token=token.access_token, token_type=token.token_type)


@router.get("/me", response_model=UserResponse)
async def current_identity(
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
) -> UserResponse:
    return UserResponse(user_id=user.user_id, role=user.role)
