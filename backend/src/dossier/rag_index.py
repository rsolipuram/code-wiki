"""Dossier RAG index — embeds findings into Qdrant for semantic retrieval.

Facet agents write findings → DossierManager → rag_index.index_dossier()
→ Qdrant `dossier_findings` collection.

The wiki generation pipeline then queries this index for contextual enrichment.
"""

import logging
import uuid
from typing import Any, Optional

from src.dossier.schema import Dossier, SecurityFinding, TechnicalDebtItem
from src.llm.embeddings import embed_batch
from src.storage.vector_db import COLLECTION_CODE_ENTITIES, delete_by_filter, upsert

logger = logging.getLogger(__name__)

COLLECTION = "dossier_findings"


def _finding_to_text(finding: Any) -> str:
    """Serialize a finding to a plain text string for embedding."""
    parts: list[str] = []
    if hasattr(finding, "type"):
        parts.append(f"Type: {finding.type}")
    if hasattr(finding, "description"):
        parts.append(f"Description: {finding.description}")
    if hasattr(finding, "related_files") and finding.related_files:
        parts.append(f"Files: {', '.join(finding.related_files)}")
    if hasattr(finding, "related_modules") and finding.related_modules:
        parts.append(f"Modules: {', '.join(finding.related_modules)}")
    if hasattr(finding, "evidence_lines") and finding.evidence_lines:
        parts.append(f"Evidence: {'; '.join(finding.evidence_lines[:3])}")
    return "\n".join(parts)


def _build_records(dossier: Dossier) -> list[tuple[str, str, dict]]:
    """Collect (id, text, metadata) tuples from all Dossier sections."""
    records: list[tuple[str, str, dict]] = []

    # Security findings
    for finding in dossier.security:
        text = _finding_to_text(finding)
        metadata = {
            "section": "security",
            "type": finding.type,
            "severity": finding.severity.value,
            "related_files": finding.related_files,
            "related_modules": finding.related_modules,
        }
        records.append((finding.id, text, metadata))

    # Technical debt items
    if dossier.technical_debt:
        for item in dossier.technical_debt.items:
            text = f"Type: {item.type}\nFile: {item.file_path}:{item.line_number}\nDescription: {item.description}"
            metadata = {
                "section": "technical_debt",
                "type": item.type,
                "severity": item.severity.value,
                "related_files": [item.file_path],
                "related_modules": [],
            }
            records.append((item.id, text, metadata))

    # Conflicts
    for conflict in dossier.conflicts:
        text = (
            f"Conflict between {conflict.facet_a} and {conflict.facet_b}.\n"
            f"{conflict.facet_a} says: {conflict.finding_a}\n"
            f"{conflict.facet_b} says: {conflict.finding_b}\n"
            f"Context: {conflict.why_both_coexist}"
        )
        metadata = {
            "section": "conflicts",
            "type": "conflict",
            "severity": "info",
            "related_files": [],
            "related_modules": [],
        }
        records.append((conflict.id, text, metadata))

    # Drop records with blank text — empty vectors waste index space and produce junk search results
    records = [(id_, text, payload) for id_, text, payload in records if text.strip()]
    return records


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
    upsert(
        collection=COLLECTION_CODE_ENTITIES,
        ids=ids,
        vectors=vectors,
        payloads=payloads,
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
