"""LM Studio client using raw OpenAI SDK with retry logic and Redis response caching."""

import hashlib
import json
import logging
from typing import Any, Optional

import httpx
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import get_settings
from src.storage import cache as cache_store

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        _client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=120.0,
        )
    return _client


def _cache_key(messages: list[dict[str, str]], **kwargs: Any) -> str:
    payload = json.dumps({"messages": messages, **kwargs}, sort_keys=True)
    return "llm:" + hashlib.sha256(payload.encode()).hexdigest()[:32]


@retry(
    retry=retry_if_exception_type((httpx.TimeoutException, Exception)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _call_llm(
    messages: list[dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> str:
    """Raw LLM call with retry. Raises on final failure."""
    settings = get_settings()
    response = get_client().chat.completions.create(
        model=model or settings.llm_model,
        messages=messages,  # type: ignore[arg-type]
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


def chat(
    messages: list[dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    cache_ttl: Optional[int] = 3600,
) -> str:
    """Send a chat completion request with optional Redis caching.

    Args:
        messages: OpenAI-format message list.
        model: Override model name (defaults to settings.llm_model).
        temperature: Sampling temperature.
        max_tokens: Maximum tokens in response.
        cache_ttl: Cache TTL seconds. None disables caching.

    Returns:
        Response content string.
    """
    key = _cache_key(messages, model=model, temperature=temperature, max_tokens=max_tokens)

    if cache_ttl is not None:
        cached = cache_store.get(key)
        if cached is not None:
            logger.debug("LLM cache hit: %s", key[:16])
            return str(cached)

    try:
        content = _call_llm(messages, model=model, temperature=temperature, max_tokens=max_tokens)
    except Exception:
        logger.error("LM Studio unavailable after retries")
        raise

    if cache_ttl is not None:
        cache_store.set(key, content, ttl=cache_ttl)

    return content
