"""
JWT creation / verification and at-rest encryption of third-party secrets.
Access tokens are short-lived (15 min); refresh tokens long-lived (30 days).
"""

import base64
import hashlib
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

settings = get_settings()

# Fernet key derived from the JWT secret (domain-separated), so no extra config is needed.
_fernet = Fernet(
    base64.urlsafe_b64encode(hashlib.sha256(b"devreview:fernet:" + settings.JWT_SECRET_KEY.encode()).digest())
)


# ── JWT utilities ──────────────────────────────────────────────────────────────

def _create_token(subject: str, expires_delta: timedelta, extra: dict | None = None) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(subject),
        "iat": now,
        "exp": now + expires_delta,
        **(extra or {}),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str, extra: dict | None = None) -> str:
    return _create_token(
        subject=user_id,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra={"type": "access", **(extra or {})},
    )


def create_refresh_token(user_id: str, session_id: str) -> str:
    return _create_token(
        subject=user_id,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        extra={"type": "refresh", "sid": session_id},
    )


def create_state_token() -> str:
    """Signed, short-lived OAuth ``state`` value (CSRF protection for the login flow)."""
    return _create_token(subject="oauth", expires_delta=timedelta(minutes=10), extra={"type": "oauth_state"})


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT.
    Raises jwt.PyJWTError on invalid / expired tokens.
    """
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def get_token_subject(token: str) -> str:
    """Return the 'sub' claim or raise jwt.PyJWTError."""
    sub = decode_token(token).get("sub")
    if not sub:
        raise jwt.InvalidTokenError("Token missing subject")
    return sub


# ── Secret encryption ──────────────────────────────────────────────────────────

def encrypt_secret(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    """Return the plaintext, or None if missing/undecryptable (user must log in again)."""
    if not value:
        return None
    try:
        return _fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        return None
