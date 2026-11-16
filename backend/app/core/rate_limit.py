"""Shared rate limiter (kept out of main.py so routers can import it without a cycle)."""

import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.security import get_token_subject


def _user_or_ip(request: Request) -> str:
    """Limit per signed-in user: the client IP comes from X-Forwarded-For, which a client can forge."""
    token = request.headers.get("authorization", "").partition(" ")[2]
    try:
        return "user:" + get_token_subject(token)
    except jwt.PyJWTError:
        return get_remote_address(request)


limiter = Limiter(key_func=_user_or_ip)

# Applied to every endpoint that spends AI tokens or clones a repository.
AI_LIMIT = "10/minute"
