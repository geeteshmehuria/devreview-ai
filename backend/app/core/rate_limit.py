"""Shared rate limiter (kept out of main.py so routers can import it without a cycle)."""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Behind a proxy (Render), run uvicorn with --proxy-headers so this sees the real client IP.
limiter = Limiter(key_func=get_remote_address)

# Applied to every endpoint that spends AI tokens or clones a repository.
AI_LIMIT = "10/minute"
