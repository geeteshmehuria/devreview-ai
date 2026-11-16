"""
Redis connection pool + helper utilities.
All cache keys are namespaced under 'devreview:' to avoid collisions.
"""

import json
from collections.abc import AsyncGenerator
from typing import Any

import redis.asyncio as aioredis
import structlog

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

_pool: aioredis.ConnectionPool | None = None


def get_redis_pool() -> aioredis.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=20,
            socket_connect_timeout=2,  # fail fast so an outage doesn't stall requests
            socket_timeout=2,
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


# The cache is an optimisation: when Redis is down, reads miss and writes are
# skipped, so reviews keep working.

async def cache_get(redis: aioredis.Redis, namespace: str, *parts: str) -> Any | None:
    """Return deserialized value, or None on miss or when Redis is unavailable."""
    try:
        raw = await redis.get(_key(namespace, *parts))
    except (aioredis.RedisError, OSError) as e:
        logger.warning("cache_unavailable", op="get", error=str(e))
        return None
    return None if raw is None else json.loads(raw)


async def cache_set(
    redis: aioredis.Redis,
    namespace: str,
    value: Any,
    ttl: int,
    *parts: str,
) -> None:
    """Serialize and store value with TTL (skipped when Redis is unavailable)."""
    try:
        await redis.setex(_key(namespace, *parts), ttl, json.dumps(value))
    except (aioredis.RedisError, OSError) as e:
        logger.warning("cache_unavailable", op="set", error=str(e))


# ── Pub/sub (live events) ──────────────────────────────────────────────────────

_pubsub_pool: aioredis.ConnectionPool | None = None


def get_pubsub_pool() -> aioredis.ConnectionPool:
    """Separate pool for long-lived SSE subscriptions.

    The cache pool's 2s socket timeout would cut an idle subscription, and each open browser
    tab holds one connection here, so keeping them apart stops live updates starving the cache.
    """
    global _pubsub_pool
    if _pubsub_pool is None:
        _pubsub_pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=50,
            socket_connect_timeout=2,
            # No health_check_interval: its PINGs would cost metered Redis commands every 30s per
            # open tab. A dropped connection ends the stream and the browser reconnects instead.
        )
    return _pubsub_pool
