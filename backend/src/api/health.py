"""Health check endpoint — verifies connectivity to all backing services."""

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter

from src.config import get_settings

router = APIRouter(tags=["health"])


def _check_postgres_sync() -> dict[str, Any]:
    try:
        import psycopg2

        settings = get_settings()
        conn = psycopg2.connect(settings.database_url, connect_timeout=3)
        conn.close()
        return {"status": "healthy"}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


def _check_graph_sync() -> dict[str, Any]:
    try:
        from src.storage import graph_db

        if not graph_db.health_check():
            return {"status": "unhealthy", "error": "graph health check failed"}
        return {"status": "healthy"}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


def _check_redis_sync() -> dict[str, Any]:
    try:
        import redis as redis_lib

        settings = get_settings()
        client = redis_lib.from_url(settings.redis_url, socket_connect_timeout=3)
        client.ping()
        client.close()
        return {"status": "healthy"}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


async def _check_qdrant() -> dict[str, Any]:
    try:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.qdrant_url}/readyz")
            if resp.status_code == 200:
                return {"status": "healthy"}
            return {"status": "unhealthy", "error": f"HTTP {resp.status_code}"}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Check connectivity to all backing services."""
    postgres, graph_status, redis_status, qdrant = await asyncio.gather(
        asyncio.to_thread(_check_postgres_sync),
        asyncio.to_thread(_check_graph_sync),
        asyncio.to_thread(_check_redis_sync),
        _check_qdrant(),
    )

    services = {
        "postgres": postgres,
        "graph": graph_status,
        "qdrant": qdrant,
        "redis": redis_status,
    }

    overall = (
        "healthy"
        if all(s["status"] == "healthy" for s in services.values())
        else "degraded"
    )

    return {
        "status": overall,
        "version": "1.0.0",
        "services": services,
    }
