"""
GitHub OAuth + JWT authentication service.
Exchanges GitHub code for user data, upserts user, issues token pair.
"""

import hashlib
import uuid

import httpx
import jwt
import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import GitHubError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    decrypt_secret,
    encrypt_secret,
)
from app.models.user import User
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
    data = response.json() if response.status_code == 200 else {}
    if "access_token" not in data:
        logger.warning("github_token_exchange_failed", status=response.status_code, error=data.get("error"))
        raise GitHubError("GitHub sign-in failed. Please try again.")
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
        logger.warning("github_user_fetch_failed", status=response.status_code)
        raise GitHubError("Failed to fetch your GitHub profile")
    return response.json()


def get_github_token(user: User) -> str:
    """Return the user's decrypted GitHub token, or ask them to sign in again."""
    token = decrypt_secret(user.github_access_token)
    if not token:
        raise UnauthorizedError("GitHub authorization expired. Please sign out and sign in again.")
    return token


async def upsert_user(db: AsyncSession, github_data: dict, github_token: str) -> User:
    """
    Create or update a user from GitHub data.
    We use github_id (stable) as the lookup key — not the login (can change).
    """
    result = await db.execute(select(User).where(User.github_id == github_data["id"]))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(github_id=github_data["id"])
        db.add(user)
        logger.info("user_created", github_login=github_data["login"])

    # Keep GitHub token and profile fresh
    user.github_login = github_data["login"]
    user.github_name = github_data.get("name")
    user.github_avatar_url = github_data.get("avatar_url")
    user.github_email = github_data.get("email")
    user.github_access_token = encrypt_secret(github_token)

    await db.flush()
    return user


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _issue_tokens(user: User) -> TokenPair:
    """Create a new access/refresh pair and remember the refresh hash for rotation."""
    refresh = create_refresh_token(str(user.id))
    user.refresh_token_hash = _hash_token(refresh)
    return TokenPair(
        access_token=create_access_token(str(user.id)),
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def login_with_github(db: AsyncSession, code: str) -> tuple[TokenPair, UserPublic]:
    """Full OAuth login flow: code → tokens → user."""
    github_token = (await exchange_github_code(code))["access_token"]
    user = await upsert_user(db, await get_github_user(github_token), github_token)
    return _issue_tokens(user), UserPublic.model_validate(user)


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> TokenPair:
    """
    Rotate refresh token on each use (prevents replay attacks).
    Old refresh token is invalidated immediately.
    """
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid token type")
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise UnauthorizedError("Invalid or expired refresh token")

    user = await db.get(User, user_id)
    if not user or not user.is_active or user.refresh_token_hash != _hash_token(refresh_token):
        raise UnauthorizedError("Refresh token has been revoked")

    return _issue_tokens(user)


async def logout(user: User) -> None:
    """Invalidate refresh token on logout."""
    user.refresh_token_hash = None


async def delete_account(db: AsyncSession, user: User) -> None:
    """Permanently delete the user; the DB cascades to repositories, reviews and findings."""
    await db.execute(delete(User).where(User.id == user.id))
