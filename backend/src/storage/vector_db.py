"""Qdrant vector database client with collection management for code_entities and dossier_findings."""

from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from src.config import get_settings

# Embedding dimension — nomic-embed-text-v1.5 via LM Studio produces 768-dim vectors
EMBEDDING_DIM = 768

COLLECTION_CODE_ENTITIES = "code_entities"
COLLECTION_DOSSIER_FINDINGS = "dossier_findings"

_client: Optional[QdrantClient] = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    return _client


def ensure_collections() -> None:
    """Create required collections if they do not exist."""
    client = get_client()
    existing = {c.name for c in client.get_collections().collections}

    for collection_name in (COLLECTION_CODE_ENTITIES, COLLECTION_DOSSIER_FINDINGS):
        if collection_name not in existing:
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )


def upsert(
    collection: str,
    ids: list[str],
    vectors: list[list[float]],
    payloads: list[dict[str, Any]],
) -> None:
    """Batch-insert or update vector points.

    Args:
        collection: Collection name.
        ids: List of string UUIDs.
        vectors: Parallel list of float vectors.
        payloads: Parallel list of metadata dicts.
    """
    points = [
        PointStruct(id=_stable_id(id_), vector=vec, payload=payload)
        for id_, vec, payload in zip(ids, vectors, payloads)
    ]
    ensure_collections()
    get_client().upsert(collection_name=collection, points=points)


def search(
    collection: str,
    vector: list[float],
    limit: int = 10,
    filters: Optional[dict[str, Any]] = None,
    score_threshold: float = 0.0,
) -> list[dict[str, Any]]:
    """Semantic similarity search with optional metadata filtering.

    Args:
        collection: Collection name.
        vector: Query vector.
        filters: Dict of field→value pairs applied as AND conditions.
        score_threshold: Minimum score to include in results.

    Returns:
        List of dicts with keys: id, score, payload.
    """
    qdrant_filter = None
    if filters:
        qdrant_filter = Filter(
            must=[
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filters.items()
            ]
        )

    results = get_client().search(
        collection_name=collection,
        query_vector=vector,
        limit=limit,
        query_filter=qdrant_filter,
        score_threshold=score_threshold,
    )
    return [{"id": str(r.id), "score": r.score, "payload": r.payload} for r in results]


def delete_by_filter(collection: str, filters: dict[str, Any]) -> None:
    """Delete points matching given metadata filter."""
    from qdrant_client.models import FilterSelector

    qdrant_filter = Filter(
        must=[
            FieldCondition(key=k, match=MatchValue(value=v))
            for k, v in filters.items()
        ]
    )
    get_client().delete(
        collection_name=collection,
        points_selector=FilterSelector(filter=qdrant_filter),
    )


def _stable_id(uuid_str: str) -> str:
    """Return point ID suitable for Qdrant (strips dashes to get hex string)."""
    return uuid_str.replace("-", "")
