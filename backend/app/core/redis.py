"""
Redis connection pool + helper utilities.
All cache keys are namespaced under 'devreview:' to avoid collisions.
"""

import json
from collections.abc import AsyncGenerator
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings

settings = get_settings()

_pool: aioredis.ConnectionPool | None = None


def get_redis_pool() -> aioredis.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=20,
        )
    return _pool


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """FastAPI dependency — yields a Redis client."""
    client = aioredis.Redis(connection_pool=get_redis_pool())
    try:
        yield client
    finally:
        await client.aclose()


# ── Cache helpers ──────────────────────────────────────────────────────────────

NAMESPACE = "devreview"


def _key(namespace: str, *parts: str) -> str:
    return f"{NAMESPACE}:{namespace}:" + ":".join(parts)


async def cache_get(redis: aioredis.Redis, namespace: str, *parts: str) -> Any | None:
    """Return deserialized value or None on miss."""
    raw = await redis.get(_key(namespace, *parts))
    if raw is None:
        return None
    return json.loads(raw)


async def cache_set(
    redis: aioredis.Redis,
    namespace: str,
    value: Any,
    ttl: int,
    *parts: str,
) -> None:
    """Serialize and store value with TTL."""
    await redis.setex(_key(namespace, *parts), ttl, json.dumps(value))


async def cache_delete(redis: aioredis.Redis, namespace: str, *parts: str) -> None:
    """Invalidate a cache entry."""
    await redis.delete(_key(namespace, *parts))


async def cache_exists(redis: aioredis.Redis, namespace: str, *parts: str) -> bool:
    return bool(await redis.exists(_key(namespace, *parts)))
