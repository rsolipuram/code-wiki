"""Dossier RAG index — embeds findings into Qdrant for semantic retrieval.

Facet agents write findings → DossierManager → rag_index.index_dossier()
→ Qdrant `dossier_findings` collection.

The wiki generation pipeline then queries this index for contextual enrichment.
"""

import logging
import uuid
from typing import Any, Optional

from src.dossier.schema import Dossier
from src.llm.embeddings import embed_batch
from src.storage.vector_db import COLLECTION_CODE_ENTITIES, delete_by_filter, upsert

logger = logging.getLogger(__name__)

COLLECTION = "dossier_findings"



def _build_records(dossier: Dossier) -> list[tuple[str, str, dict]]:
    """Collect (id, text, metadata) tuples from all Dossier responses."""
    records: list[tuple[str, str, dict]] = []

    for resp in dossier.responses:
        out = resp.output
        otype = resp.output_type

        if otype == "SecurityFinding":
            text = _finding_to_text_from_dict(out)
            metadata = {
                "section": "security",
                "type": out.get("type", ""),
                "severity": out.get("severity", "info"),
                "related_files": out.get("related_files", []),
                "related_modules": out.get("related_modules", []),
            }
            records.append((out.get("id", str(uuid.uuid4())), text, metadata))

        elif otype == "TechnicalDebt":
            for item in out.get("items", []):
                text = f"Type: {item.get('type', '')}\nFile: {item.get('file_path', '')}:{item.get('line_number', 0)}\nDescription: {item.get('description', '')}"
                metadata = {
                    "section": "technical_debt",
                    "type": item.get("type", ""),
                    "severity": item.get("severity", "low"),
                    "related_files": [item.get("file_path", "")],
                    "related_modules": [],
                }
                records.append((item.get("id", str(uuid.uuid4())), text, metadata))

        elif otype == "ConflictAnalysis":
            text = (
                f"Conflict between {out.get('facet_a', '')} and {out.get('facet_b', '')}.\n"
                f"{out.get('facet_a', '')} says: {out.get('finding_a', '')}\n"
                f"{out.get('facet_b', '')} says: {out.get('finding_b', '')}\n"
                f"Context: {out.get('why_both_coexist', '')}"
            )
            metadata = {
                "section": "conflicts",
                "type": "conflict",
                "severity": "info",
                "related_files": [],
                "related_modules": [],
            }
            records.append((out.get("id", str(uuid.uuid4())), text, metadata))

    # Drop records with blank text
    records = [(id_, text, payload) for id_, text, payload in records if text.strip()]
    return records


def _finding_to_text_from_dict(out: dict) -> str:
    """Serialize a finding dict to plain text for embedding."""
    parts: list[str] = []
    if out.get("type"):
        parts.append(f"Type: {out['type']}")
    if out.get("description"):
        parts.append(f"Description: {out['description']}")
    if out.get("related_files"):
        parts.append(f"Files: {', '.join(out['related_files'])}")
    if out.get("related_modules"):
        parts.append(f"Modules: {', '.join(out['related_modules'])}")
    if out.get("evidence_lines"):
        parts.append(f"Evidence: {'; '.join(out['evidence_lines'][:3])}")
    return "\n".join(parts)


def index_entities(entities: list[Any], repo_id: str) -> None:
    """Index parsed code entities into the code_entities Qdrant collection.

    Args:
        entities: List of ParsedEntity objects from the code parser.
        repo_id: Repository ID used as a filter key.
    """
    if not entities:
        return

    texts, ids, payloads = [], [], []
    for e in entities:
        text = f"{e.entity_type} {e.qualified_name}: {e.docstring or e.signature or e.name}"
        if not text.strip():
            continue
        texts.append(text)
        # Generate a deterministic UUID from qualified_name so upserts are idempotent
        entity_id = str(uuid.uuid5(uuid.NAMESPACE_OID, e.qualified_name))
        ids.append(entity_id)
        payloads.append({
            "repo_id": repo_id,
            "name": e.name,
            "qualified_name": e.qualified_name,
            "entity_type": e.entity_type,
            "file_path": e.file_path,
            "line_start": e.line_start,
            "signature": e.signature or "",
        })

    if not texts:
        return

    logger.info("Embedding %d entities for code_entities index (repo %s)", len(texts), repo_id)
    vectors = embed_batch(texts)

    # Batch upserts to stay under Qdrant's payload size limit (~33MB)
    BATCH_SIZE = 500
    for i in range(0, len(texts), BATCH_SIZE):
        end = min(i + BATCH_SIZE, len(texts))
        upsert(
            collection=COLLECTION_CODE_ENTITIES,
            ids=ids[i:end],
            vectors=vectors[i:end],
            payloads=payloads[i:end],
        )
    logger.info("Indexed %d entities into %s", len(texts), COLLECTION_CODE_ENTITIES)


def index_dossier(dossier: Dossier, repository_id: str) -> int:
    """Embed all Dossier findings and upsert into Qdrant dossier_findings collection.

    Args:
        dossier: The populated Dossier to index.
        repository_id: Repository ID used as a filter key.

    Returns:
        Number of findings indexed.
    """
    records = _build_records(dossier)
    if not records:
        logger.info("No findings to index for repository %s", repository_id)
        return 0

    ids, texts, payloads = zip(*records)

    # Embed all texts in one batch
    logger.info(
        "Embedding %d Dossier findings for repository %s (batch size: %d)",
        len(texts), repository_id, len(texts),
    )
    try:
        vectors = embed_batch(list(texts))
    except Exception as exc:
        logger.error("Embedding batch failed for repository %s: %s", repository_id, exc)
        raise

    # Attach repository_id to each payload for filtering
    full_payloads = [{**p, "repository_id": repository_id} for p in payloads]

    logger.info("Upserting %d points into Qdrant collection %s", len(ids), COLLECTION)
    upsert(
        collection=COLLECTION,
        ids=list(ids),
        vectors=vectors,
        payloads=full_payloads,
    )

    logger.info("Indexed %d findings into %s", len(records), COLLECTION)
    return len(records)


def search_dossier(
    query: str,
    repository_id: str,
    limit: int = 10,
    section: Optional[str] = None,
    module: Optional[str] = None,
) -> list[dict]:
    """Semantic search over indexed Dossier findings.

    Args:
        query: Natural language query string.
        repository_id: Restrict results to this repository.
        limit: Maximum number of results.
        section: Filter by Dossier section (e.g. "security", "technical_debt").
        module: Filter by related_modules value.

    Returns:
        List of payload dicts from matching findings.
    """
    from src.llm.embeddings import embed
    from src.storage.vector_db import search

    vector = embed(query)
    filters: dict[str, str] = {"repository_id": repository_id}
    if section:
        filters["section"] = section
    if module:
        filters["related_modules"] = module

    results = search(collection=COLLECTION, vector=vector, limit=limit, filters=filters)
    return [r["payload"] for r in results]


def clear_dossier_index(repository_id: str) -> None:
    """Remove all Dossier findings for a repository from Qdrant."""
    delete_by_filter(collection=COLLECTION, filters={"repository_id": repository_id})
    logger.info("Cleared Dossier index for repository %s", repository_id)
