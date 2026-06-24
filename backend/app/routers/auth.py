"""Auth router — GitHub OAuth endpoints."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.auth import GitHubOAuthRequest, RefreshRequest, TokenPair, UserPublic
from app.services.auth_service import login_with_github, logout, refresh_access_token

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.get("/github/url")
async def github_oauth_url():
    """Return the GitHub OAuth authorization URL for the frontend to redirect to."""
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.GITHUB_CLIENT_ID}"
        f"&scope=repo,read:user,user:email"
        f"&redirect_uri={settings.GITHUB_CALLBACK_URL}"
    )
    return {"url": url}


@router.post("/github/callback", response_model=dict)
async def github_callback(
    payload: GitHubOAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange GitHub OAuth code for JWT tokens."""
    tokens, user = await login_with_github(db, payload.code)
    return {"tokens": tokens.model_dump(), "user": user.model_dump()}


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Issue new access + refresh token pair (rotates refresh token)."""
    return await refresh_access_token(db, payload.refresh_token)


@router.post("/logout")
async def logout_user(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the current user's refresh token."""
    await logout(db, str(current_user.id))
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return UserPublic.model_validate(current_user)
