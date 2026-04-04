"""Chat context builder — RAG retrieval for chat assistant (T092).

Retrieves relevant wiki pages, code entities, and Dossier findings from Qdrant
for a given user question using semantic similarity search.
"""

import logging
from typing import Any

from src.llm.embeddings import embed
from src.storage import vector_db

logger = logging.getLogger(__name__)

# Max items to retrieve per collection
_ENTITY_LIMIT = 8
_DOSSIER_LIMIT = 4
_SCORE_THRESHOLD = 0.25


def build_context(
    question: str,
    repository_id: str,
    max_tokens: int = 6000,
) -> dict[str, Any]:
    """Retrieve relevant context for a chat question.

    Args:
        question: The user's natural language question.
        repository_id: Repository UUID to scope the search.
        max_tokens: Approximate token budget for context (each char ~0.25 tokens).

    Returns:
        Dict with keys: entities, dossier_findings, context_text, references.
        - entities: list of matching code entity payloads
        - dossier_findings: list of matching dossier finding payloads
        - context_text: formatted string for LLM prompt
        - references: list of {type, id, title} for API response
    """
    try:
        query_vector = embed(question)
    except Exception as exc:
        logger.warning("Embedding failed for chat query: %s", exc)
        return _empty_context()

    # Search code entities
    entities = _search_entities(query_vector, repository_id)

    # Search dossier findings
    dossier_findings = _search_dossier(query_vector, repository_id)

    # Build formatted context string
    context_text = _format_context(entities, dossier_findings, max_tokens)

    # Build references list (for API response)
    references = _build_references(entities, dossier_findings)

    return {
        "entities": entities,
        "dossier_findings": dossier_findings,
        "context_text": context_text,
        "references": references,
    }


def _search_entities(
    query_vector: list[float], repository_id: str
) -> list[dict[str, Any]]:
    """Search code_entities collection filtered by repository_id."""
    try:
        results = vector_db.search(
            collection=vector_db.COLLECTION_CODE_ENTITIES,
            vector=query_vector,
            limit=_ENTITY_LIMIT,
            # code_entities are indexed with "repo_id" (see dossier.rag_index.index_entities)
            filters={"repo_id": repository_id},
            score_threshold=_SCORE_THRESHOLD,
        )
        return [r["payload"] for r in results if r.get("payload")]
    except Exception as exc:
        logger.warning("Code entity search failed: %s", exc)
        return []


def _search_dossier(
    query_vector: list[float], repository_id: str
) -> list[dict[str, Any]]:
    """Search dossier_findings collection filtered by repository_id."""
    try:
        results = vector_db.search(
            collection=vector_db.COLLECTION_DOSSIER_FINDINGS,
            vector=query_vector,
            limit=_DOSSIER_LIMIT,
            filters={"repository_id": repository_id},
            score_threshold=_SCORE_THRESHOLD,
        )
        return [r["payload"] for r in results if r.get("payload")]
    except Exception as exc:
        logger.warning("Dossier search failed: %s", exc)
        return []


def _format_context(
    entities: list[dict[str, Any]],
    dossier_findings: list[dict[str, Any]],
    max_tokens: int,
) -> str:
    """Format retrieved context into a string for the LLM prompt."""
    char_budget = max_tokens * 4  # rough chars-per-token
    parts: list[str] = []

    if entities:
        parts.append("## Relevant Code Entities\n")
        for e in entities:
            name = e.get("qualified_name") or e.get("name", "unknown")
            etype = e.get("entity_type", "")
            sig = e.get("signature", "")
            doc = e.get("docstring", "")
            file_path = e.get("file_path", "")
            chunk = f"### {name} ({etype})\nFile: {file_path}\n"
            if sig:
                chunk += f"Signature: `{sig}`\n"
            if doc:
                chunk += f"Docstring: {doc[:200]}\n"
            parts.append(chunk)

    if dossier_findings:
        parts.append("\n## Codebase Analysis Findings\n")
        for f in dossier_findings:
            section = f.get("section", "")
            desc = f.get("description", str(f)[:150])
            parts.append(f"[{section}] {desc}\n")

    context_text = "\n".join(parts)
    if len(context_text) > char_budget:
        context_text = context_text[:char_budget] + "\n... (truncated)"

    return context_text or "No relevant context found."


def _build_references(
    entities: list[dict[str, Any]],
    dossier_findings: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Build API reference objects from retrieved items."""
    refs: list[dict[str, str]] = []

    for e in entities:
        entity_id = e.get("entity_id") or e.get("id") or ""
        name = e.get("qualified_name") or e.get("name", "entity")
        refs.append({"type": "code_entity", "id": str(entity_id), "title": name})

    for f in dossier_findings:
        section = f.get("section", "finding")
        desc = f.get("description", "")[:60]
        refs.append({"type": "dossier_finding", "id": section, "title": desc or section})

    return refs


def _empty_context() -> dict[str, Any]:
    return {
        "entities": [],
        "dossier_findings": [],
        "context_text": "No relevant context found.",
        "references": [],
    }
