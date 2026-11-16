"""
Per-user live events: jobs publish to Redis pub/sub, the SSE endpoint relays them to the browser.

Pub/sub is fire-and-forget — a browser that is not connected misses the event. That is fine
because every event describes state that is also saved in Postgres; the frontend refetches on
(re)connect, so it can never get stuck on a stale state.
"""

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as aioredis
import structlog

from app.core.redis import get_pubsub_pool

logger = structlog.get_logger()

CHANNEL_PREFIX = "devreview:events:"
HEARTBEAT_SECONDS = 20.0  # keeps proxies (Render, mobile networks) from closing an idle stream

# Event types — keep in sync with frontend/lib/api/events.ts
INDEX_STATUS = "index_status"   # payload: repo_id + IndexStatusOut fields
REPO_STATUS = "repo_status"     # payload: repo_id + status


def channel_for(user_id: uuid.UUID | str) -> str:
    return f"{CHANNEL_PREFIX}{user_id}"


async def publish_event(redis: aioredis.Redis, user_id: uuid.UUID | str, event: dict[str, Any]) -> None:
    """Best effort: a failed publish must never fail the job (the result is already saved)."""
    try:
        await redis.publish(channel_for(user_id), json.dumps(event, default=str))
    except (aioredis.RedisError, OSError) as e:
        logger.warning("event_publish_failed", user_id=str(user_id), type=event.get("type"), error=str(e))


def format_sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def event_stream(
    user_id: uuid.UUID | str,
    redis: aioredis.Redis | None = None,
    heartbeat_seconds: float = HEARTBEAT_SECONDS,
) -> AsyncIterator[str]:
    """Yield SSE text for one user's channel until the client disconnects.

    `ready` is sent once subscribed, so the client knows it will not miss later events and can
    refetch anything that changed before it connected. `job` carries each published event.
    """
    client = redis or aioredis.Redis(connection_pool=get_pubsub_pool())
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    try:
        await pubsub.subscribe(channel_for(user_id))
        yield format_sse("ready", {})
        last_sent = time.monotonic()
        while True:
            # Waits on the socket; sends no Redis commands, so an idle stream is free on metered Redis.
            message = await pubsub.get_message(timeout=1.0)
            if message and message.get("type") == "message":
                try:
                    yield format_sse("job", json.loads(message["data"]))
                except (TypeError, ValueError):
                    logger.warning("event_malformed", user_id=str(user_id))
                last_sent = time.monotonic()
                continue
            if time.monotonic() - last_sent >= heartbeat_seconds:
                yield ": ping\n\n"  # SSE comment — ignored by the client parser
                last_sent = time.monotonic()
    except (aioredis.RedisError, OSError) as e:
        logger.warning("event_stream_redis_error", user_id=str(user_id), error=str(e))
        yield format_sse("error", {"message": "Live updates are unavailable right now."})
    finally:
        try:
            await pubsub.aclose()
        finally:
            if redis is None:
                await client.aclose()
