"""Redis cache utility with get/set/delete and TTL support."""

import json
from typing import Any, Optional

import redis as redis_lib

from src.config import get_settings

_client: Optional[redis_lib.Redis] = None  # type: ignore[type-arg]


def get_client() -> redis_lib.Redis:  # type: ignore[type-arg]
    global _client
    if _client is None:
        settings = get_settings()
        _client = redis_lib.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=3,
        )
    return _client


def get(key: str) -> Optional[Any]:
    """Retrieve a value, returning None on miss or connection failure."""
    try:
        raw = get_client().get(key)
        return json.loads(raw) if raw is not None else None
    except Exception:
        return None


def set(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """Store a JSON-serialisable value with optional TTL in seconds.

    Returns True on success, False on failure.
    """
    try:
        serialised = json.dumps(value)
        if ttl is not None:
            get_client().setex(key, ttl, serialised)
        else:
            get_client().set(key, serialised)
        return True
    except Exception:
        return False


def delete(key: str) -> bool:
    """Remove a key. Returns True if key existed."""
    try:
        return bool(get_client().delete(key))
    except Exception:
        return False


def ping() -> bool:
    """Check Redis connectivity."""
    try:
        return get_client().ping()
    except Exception:
        return False
