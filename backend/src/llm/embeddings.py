"""Sentence-transformers embedding utility using all-MiniLM-L6-v2 (384-dim)."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_model = None
MODEL_NAME = "all-MiniLM-L6-v2"


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model %s (first call only)", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed(text: str) -> list[float]:
    """Encode a single string into a 384-dimensional vector."""
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_batch(texts: list[str], batch_size: int = 64) -> list[list[float]]:
    """Encode a list of strings into 384-dimensional vectors.

    Args:
        texts: List of strings to encode.
        batch_size: Encoding batch size (trades memory for speed).

    Returns:
        List of float vectors, one per input string.
    """
    if not texts:
        return []

    model = _get_model()
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=len(texts) > 100,
    )
    return [v.tolist() for v in vectors]
