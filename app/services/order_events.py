import json
from asyncio import get_running_loop
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from functools import lru_cache

from redis import Redis as SyncRedis
from redis.asyncio import Redis as AsyncRedis

from app.models.orders import OrderStatus
from app.utils.config import settings


def order_status_channel(order_id: int) -> str:
    """Return the Redis channel used by one order's status stream."""
    return f"orders:{order_id}:status"


@lru_cache
def get_redis_client() -> SyncRedis:
    """Create one reusable Redis client for status publishers."""
    if not settings.REDIS_URL:
        raise RuntimeError("REDIS_URL is required for live order updates")
    return SyncRedis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )


def publish_order_status(
    order_id: int,
    order_status: OrderStatus,
) -> None:
    
    """Publish a committed order-status change to Redis."""
    
    event = {
        "order_id": order_id,
        "status": order_status.value,
        "changed_at": datetime.now(timezone.utc).isoformat(),
    }
    get_redis_client().publish(
        order_status_channel(order_id),
        json.dumps(event),
    )


def get_async_redis_client() -> AsyncRedis:
    """Create a Redis client owned by one SSE connection."""
    if not settings.REDIS_URL:
        raise RuntimeError("REDIS_URL is required for live order updates")
    return AsyncRedis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )


def format_sse_event(event: str, data: str) -> str:
    """Format one message using the Server-Sent Events protocol."""
    return f"event: {event}\ndata: {data}\n\n"


async def stream_order_status(order_id: int) -> AsyncIterator[str]:
    """Yield Redis messages for one order as SSE-formatted strings."""
    redis = get_async_redis_client()
    pubsub = redis.pubsub()
    channel = order_status_channel(order_id)
    await pubsub.subscribe(channel)

    loop = get_running_loop()
    last_heartbeat = loop.time()

    try:
        yield format_sse_event(
            "connected",
            json.dumps({"order_id": order_id}),
        )

        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )
            if message is not None and message.get("type") == "message":
                yield format_sse_event("status", message["data"])

            if loop.time() - last_heartbeat >= 15:
                yield ": keep-alive\n\n"
                last_heartbeat = loop.time()
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await redis.aclose()
