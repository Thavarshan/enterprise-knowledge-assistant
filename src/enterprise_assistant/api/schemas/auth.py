"""Define login and identity request and response contracts.

The request accepts only username and password. Role is returned from the
server-resolved identity and is never accepted in the login request.
"""

from pydantic import BaseModel, ConfigDict, Field

from enterprise_assistant.security.authorization import Role


class TokenRequest(BaseModel):
    """Validate credentials submitted to the development login route.

    Extra fields, including role claims, are rejected. The model constrains
    text lengths but does not verify a password; AuthService performs that
    check against local development configuration.

    Attributes:
        username: Configured development account name.
        password: Secret supplied for login; do not log or echo it.
    """
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    """Represent an issued opaque bearer token.

    The token is held by the client and resolved by the API process; it has
    no expiry or persistence in the current development implementation.

    Attributes:
        access_token: Random bearer credential returned after login.
        token_type: HTTP authorization scheme, normally bearer.
    """
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Expose the server-resolved identity returned by the API.

    The role is derived from the configured account and token store, not
    accepted as a client authorization claim.

    Attributes:
        user_id: Stable configured username for this development account.
        role: Backend-assigned application role.
    """
    user_id: str
    role: Role
