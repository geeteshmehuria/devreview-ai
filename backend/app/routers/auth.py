"""Auth router — GitHub OAuth endpoints."""

from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import AppException, UnauthorizedError
from app.core.security import create_state_token, decode_token
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.auth import GitHubOAuthRequest, RefreshRequest, TokenPair, UserPublic
from app.services.auth_service import delete_account, login_with_github, logout, refresh_access_token

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.get("/github/url")
async def github_oauth_url():
    """Return the GitHub OAuth authorization URL for the frontend to redirect to.

    Also returns a signed, short-lived ``state``. The frontend keeps it and checks
    GitHub echoes the same value back; the backend verifies its signature on the
    callback (CSRF protection for the login flow).
    """
    if not settings.GITHUB_CLIENT_ID:
        raise AppException("GitHub OAuth is not configured (missing GITHUB_CLIENT_ID)")

    state = create_state_token()
    params = urlencode(
        {
            "client_id": settings.GITHUB_CLIENT_ID,
            "scope": "repo,read:user,user:email",
            "redirect_uri": settings.GITHUB_CALLBACK_URL,
            "state": state,
        }
    )
    return {"url": f"https://github.com/login/oauth/authorize?{params}", "state": state}


@router.post("/github/callback", response_model=dict)
async def github_callback(
    payload: GitHubOAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange GitHub OAuth code for JWT tokens."""
    try:
        if decode_token(payload.state).get("type") != "oauth_state":
            raise UnauthorizedError("Invalid login state")
    except jwt.PyJWTError:
        raise UnauthorizedError("Login session expired. Please try signing in again.")

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
async def logout_user(current_user: User = Depends(get_current_user)):
    """Revoke the current user's refresh token."""
    await logout(current_user)
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return UserPublic.model_validate(current_user)


@router.delete("/me", status_code=204)
async def delete_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete the account and all of its reviews, repositories and findings."""
    await delete_account(db, current_user)
