"""Auth-related Pydantic schemas."""

from uuid import UUID

from pydantic import BaseModel, field_validator


class GitHubOAuthRequest(BaseModel):
    code: str
    state: str | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class UserPublic(BaseModel):
    id: str
    github_login: str
    github_name: str | None
    github_avatar_url: str | None
    github_email: str | None
    role: str

    model_config = {"from_attributes": True}

    @field_validator("id", mode="before")
    @classmethod
    def coerce_uuid_to_str(cls, v: str | UUID) -> str:
        """ORM hands us a UUID primary key; the API contract is a string."""
        return str(v) if isinstance(v, UUID) else v
