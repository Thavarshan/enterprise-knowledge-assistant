"""Authentication request and response contracts."""

from pydantic import BaseModel, ConfigDict, Field

from enterprise_assistant.security.authorization import Role


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    user_id: str
    role: Role
