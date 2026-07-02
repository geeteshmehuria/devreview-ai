"""
GitHub OAuth + JWT authentication service.
Exchanges GitHub code for user data, upserts user, issues token pair.
"""

import hashlib
import secrets

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.core.exceptions import GitHubError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User, UserSettings
from app.schemas.auth import TokenPair, UserPublic

logger = structlog.get_logger()
settings = get_settings()

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


async def exchange_github_code(code: str) -> dict:
    """Exchange OAuth code for GitHub access token."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                # Must match the redirect_uri sent in the authorize request.
                "redirect_uri": settings.GITHUB_CALLBACK_URL,
            },
            headers={"Accept": "application/json"},
        )
    if response.status_code != 200:
        raise GitHubError(f"GitHub token exchange failed: {response.text}")

    data = response.json()
    if "error" in data:
        raise GitHubError(f"GitHub OAuth error: {data.get('error_description', data['error'])}")
    return data


async def get_github_user(access_token: str) -> dict:
    """Fetch GitHub user profile using their access token."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
    if response.status_code != 200:
        raise GitHubError(f"Failed to fetch GitHub user: {response.text}")
    return response.json()


async def upsert_user(db: AsyncSession, github_data: dict, github_token: str) -> User:
    """
    Create or update a user from GitHub data.
    We use github_id (stable) as the lookup key — not the login (can change).
    """
    github_id = github_data["id"]

    result = await db.execute(select(User).where(User.github_id == github_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            github_id=github_id,
            github_login=github_data["login"],
            github_name=github_data.get("name"),
            github_avatar_url=github_data.get("avatar_url"),
            github_email=github_data.get("email"),
            github_access_token=github_token,
        )
        db.add(user)
        await db.flush()  # get the id

        # Auto-create default settings
        db.add(UserSettings(user_id=user.id))
        logger.info("user_created", github_login=user.github_login)
    else:
        # Keep GitHub token and profile fresh
        user.github_login = github_data["login"]
        user.github_name = github_data.get("name")
        user.github_avatar_url = github_data.get("avatar_url")
        user.github_email = github_data.get("email")
        user.github_access_token = github_token
        logger.info("user_updated", github_login=user.github_login)

    await db.flush()
    return user


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def login_with_github(db: AsyncSession, code: str) -> tuple[TokenPair, UserPublic]:
    """Full OAuth login flow: code → tokens → user."""
    github_token_data = await exchange_github_code(code)
    access_token = github_token_data["access_token"]

    github_user = await get_github_user(access_token)
    user = await upsert_user(db, github_user, access_token)

    # Issue our own JWTs
    jwt_access = create_access_token(str(user.id))
    jwt_refresh = create_refresh_token(str(user.id))

    # Store hashed refresh token for rotation validation
    user.refresh_token_hash = _hash_token(jwt_refresh)

    token_pair = TokenPair(
        access_token=jwt_access,
        refresh_token=jwt_refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    user_public = UserPublic.model_validate(user)
    return token_pair, user_public


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> TokenPair:
    """
    Rotate refresh token on each use (prevents replay attacks).
    Old refresh token is invalidated immediately.
    """
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid token type")
        user_id = payload["sub"]
    except Exception:
        raise UnauthorizedError("Invalid or expired refresh token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or user.refresh_token_hash != _hash_token(refresh_token):
        raise UnauthorizedError("Refresh token has been revoked")

    new_access = create_access_token(str(user.id))
    new_refresh = create_refresh_token(str(user.id))
    user.refresh_token_hash = _hash_token(new_refresh)

    return TokenPair(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def logout(db: AsyncSession, user_id: str) -> None:
    """Invalidate refresh token on logout."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.refresh_token_hash = None
