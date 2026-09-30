"""
FastAPI dependency for extracting and validating the current user from JWT.
Usage: current_user: User = Depends(get_current_user)
"""

import uuid

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_token
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise UnauthorizedError("No authentication token provided")

    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise UnauthorizedError("Invalid token type")
        user_id = uuid.UUID(payload.get("sub", ""))
    except (jwt.PyJWTError, ValueError):
        raise UnauthorizedError("Invalid or expired token")

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    return user
