"""Redis pub/sub helpers for real-time pipeline progress streaming.

Agents publish progress events to a Redis channel keyed by repo ID.
The SSE endpoint subscribes to that channel and streams events to the frontend.
"""

import asyncio
import json
import logging
import time
from typing import AsyncGenerator, Optional

from src.storage import cache

logger = logging.getLogger(__name__)

# Keepalive interval — if no real event arrives within this many seconds,
# the subscriber yields None so the SSE endpoint can emit a comment.
_KEEPALIVE_SECONDS = 15.0


def publish_progress(repo_id: str, event: dict) -> None:
    """Publish a progress event to Redis pub/sub channel."""
    try:
        client = cache.get_client()
        client.publish(f"progress:{repo_id}", json.dumps(event))
    except Exception:
        logger.debug("Failed to publish progress event for %s", repo_id, exc_info=True)


async def subscribe_progress(repo_id: str) -> AsyncGenerator[Optional[dict], None]:
    """Async generator yielding progress events from Redis pub/sub.

    Uses asyncio.to_thread() to avoid blocking the event loop on the
    synchronous Redis get_message() call.

    Yields:
        dict — a parsed progress event from the channel.
        None — a keepalive signal (no real event within _KEEPALIVE_SECONDS).
    """
    client = cache.get_client()
    pubsub = client.pubsub()
    pubsub.subscribe(f"progress:{repo_id}")
    last_event_time = time.monotonic()
    try:
        while True:
            message = await asyncio.to_thread(
                pubsub.get_message,
                ignore_subscribe_messages=True,
                timeout=1.0,
            )
            if message and message["type"] == "message":
                last_event_time = time.monotonic()
                try:
                    yield json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
            else:
                # Emit keepalive signal if idle too long
                if time.monotonic() - last_event_time > _KEEPALIVE_SECONDS:
                    last_event_time = time.monotonic()
                    yield None
                await asyncio.sleep(0.1)
    finally:
        pubsub.unsubscribe(f"progress:{repo_id}")
        pubsub.close()
