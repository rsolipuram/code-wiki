"""Embedding utility using LM Studio's OpenAI-compatible /v1/embeddings endpoint."""

import logging
import time
from typing import Optional

from openai import OpenAI

from src.config import get_settings

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None

_MAX_RETRIES = 2
_INITIAL_DELAY = 2  # seconds — give LM Studio time to load/swap models


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        _client = OpenAI(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            timeout=120.0,
        )
    return _client


def _retry_create(client: OpenAI, model: str, inp):
    """Call embeddings.create with retries for transient LM Studio model-load failures."""
    delay = _INITIAL_DELAY
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return client.embeddings.create(model=model, input=inp)
        except Exception as exc:
            if attempt >= _MAX_RETRIES:
                raise
            logger.warning("Embedding attempt %d/%d failed: %s — retrying in %ds",
                           attempt, _MAX_RETRIES, exc, delay)
            time.sleep(delay)
            delay = min(delay * 2, 15)


def embed(text: str) -> list[float]:
    """Encode a single string into a vector via the configured embeddings API."""
    settings = get_settings()
    client = _get_client()
    response = _retry_create(client, settings.embedding_model, text)
    return response.data[0].embedding


def embed_batch(texts: list[str], batch_size: int = 64) -> list[list[float]]:
    """Encode a list of strings into vectors via the configured embeddings API.

    Args:
        texts: List of strings to encode.
        batch_size: Number of texts per API call.

    Returns:
        List of float vectors, one per input string.
    """
    if not texts:
        return []

    settings = get_settings()
    vectors: list[list[float]] = []
    client = _get_client()

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = _retry_create(client, settings.embedding_model, batch)
        sorted_data = sorted(response.data, key=lambda x: x.index)
        vectors.extend([item.embedding for item in sorted_data])

    logger.info("Embedded %d texts via %s (%s)", len(texts), settings.embedding_base_url, settings.embedding_model)
    return vectors
