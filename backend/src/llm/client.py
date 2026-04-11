"""LM Studio client using raw OpenAI SDK with retry logic and Redis response caching."""

import hashlib
import inspect
import json
import logging
import time
from uuid import uuid4
from typing import Any, Optional

import openai
from openai import OpenAI

from src.config import get_settings
from src.llm.providers import resolve_provider
from src.storage import cache as cache_store

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        config = resolve_provider(settings)
        _client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=config.timeout,
        )
    return _client


def _cache_key(messages: list[dict[str, str]], **kwargs: Any) -> str:
    config = resolve_provider(get_settings())
    payload = json.dumps({"base_url": config.base_url, "messages": messages, **kwargs}, sort_keys=True)
    return "llm:" + hashlib.sha256(payload.encode()).hexdigest()[:32]


def _call_llm(
    messages: list[dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> tuple[str, int]:
    """Raw LLM call with bounded retry. Returns content and retry count."""
    config = resolve_provider(get_settings())
    resolved_model = model or config.model
    last_exc: Exception | None = None
    delay_seconds = 2

    # Qwen3 thinking models may consume extra tokens for internal reasoning.
    # When thinking is enabled, scale up max_tokens to leave room for both the
    # reasoning chain and the actual answer.  When thinking is off the multiplier
    # is harmless but wastes budget — keep it at 1x in that case.
    effective_max_tokens = max_tokens
    msgs = messages

    for attempt in range(1, 4):
        try:
            response = get_client().chat.completions.create(
                model=resolved_model,
                messages=msgs,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=effective_max_tokens,
            )
            msg = response.choices[0].message
            content = msg.content or ""
            # Qwen3 thinking mode puts output in reasoning_content
            if not content.strip():
                content = getattr(msg, "reasoning_content", "") or ""
            if not content.strip():
                raise ValueError("empty_response")
            return content, attempt - 1
        except Exception as exc:  # noqa: BLE001 - upstream client throws mixed exception types
            last_exc = exc
            if attempt >= 3:
                raise
            if isinstance(exc, openai.APIStatusError):
                status_code = getattr(exc, "status_code", None)
                if status_code not in config.retryable_statuses:
                    raise
                sleep_seconds = delay_seconds
                if status_code == 429:
                    retry_after = None
                    try:
                        response = getattr(exc, "response", None)
                        if response is not None:
                            retry_after_header = response.headers.get("Retry-After")
                            if retry_after_header is not None:
                                retry_after = int(float(retry_after_header))
                    except Exception:  # noqa: BLE001
                        retry_after = None
                    if retry_after is not None:
                        sleep_seconds = max(0, min(retry_after, 60))
                logger.warning(
                    "LLM call attempt %d/3 failed with status %s. Retrying in %ss.",
                    attempt,
                    status_code,
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)
                delay_seconds = min(delay_seconds * 2, 10)
                continue

            if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
                logger.warning("LLM connection attempt %d/3 failed: %s", attempt, exc)
                time.sleep(delay_seconds)
                delay_seconds = min(delay_seconds * 2, 10)
                continue

            logger.warning("LLM call attempt %d/3 failed: %s", attempt, exc)
            time.sleep(delay_seconds)
            delay_seconds = min(delay_seconds * 2, 10)

    raise RuntimeError("LLM call failed after retries") from last_exc


def chat(
    messages: list[dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    cache_ttl: Optional[int] = 3600,
    trace_context: Optional[dict[str, Any]] = None,
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
    config = resolve_provider(get_settings())
    effective_model = model or config.model
    key = _cache_key(messages, model=effective_model, temperature=temperature, max_tokens=max_tokens)
    caller = inspect.stack()[1]
    context = {
        "call_id": (trace_context or {}).get("call_id", uuid4().hex[:12]),
        "stage": (trace_context or {}).get("stage", "unknown"),
        "component": (trace_context or {}).get("component", "unknown"),
        "analysis_id": (trace_context or {}).get("analysis_id"),
        "caller_file": caller.filename,
        "caller_line": caller.lineno,
        "model": effective_model,
    }

    if cache_ttl is not None:
        cached = cache_store.get(key)
        if cached is not None:
            logger.debug("LLM cache hit: %s", key[:16])
            logger.info(
                "LLM_TELEMETRY %s",
                json.dumps(
                    {
                        **context,
                        "event": "llm_call",
                        "status": "success",
                        "cache_hit": True,
                        "retry_count": 0,
                        "duration_ms": 0,
                        "response_chars": len(str(cached)),
                    },
                    sort_keys=True,
                ),
            )
            return str(cached)

    started = time.perf_counter()
    try:
        content, retry_count = _call_llm(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.error("LLM provider unavailable after retries: %s", exc)
        logger.error(
            "LLM_TELEMETRY %s",
            json.dumps(
                {
                    **context,
                    "event": "llm_call",
                    "status": "failure",
                    "cache_hit": False,
                    "duration_ms": duration_ms,
                    "retry_count": 2,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                },
                sort_keys=True,
            ),
        )
        raise

    duration_ms = int((time.perf_counter() - started) * 1000)
    if cache_ttl is not None and content.strip():
        cache_store.set(key, content, ttl=cache_ttl)

    logger.info(
        "LLM_TELEMETRY %s",
        json.dumps(
            {
                **context,
                "event": "llm_call",
                "status": "success",
                "cache_hit": False,
                "duration_ms": duration_ms,
                "retry_count": retry_count,
                "response_chars": len(content),
            },
            sort_keys=True,
        ),
    )

    return content
