"""Qdrant code entity search tool for V4 wiki agents.

Wraps the vector_db.search() and llm/embeddings.embed() functions
as a LangChain tool that the Code Embedder agent can use to find
code entities by symbol name or semantic description.
"""

import json
import logging
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

MAX_RESULTS = 8


def make_qdrant_tools(repository_id: str) -> list:
    """Create Qdrant code entity search tools scoped to a repository.

    Args:
        repository_id: UUID of the repository to search within.

    Returns:
        List of LangChain tool functions.
    """

    @tool
    def search_code_entities(
        query: str,
        entity_type: Optional[str] = None,
        limit: int = 5,
    ) -> str:
        """Search for code entities (functions, classes, modules) by name or description.

        Use this to find the file path and line number of a symbol when you know
        its name or a description of what it does. Results include:
        - name and qualified_name
        - entity_type (function, class, module, etc.)
        - file_path (relative to repo root)
        - line_start (line number where the entity is defined)
        - signature (if available)

        Args:
            query: Symbol name or natural language description.
                   Examples: "triage_agent", "function that handles authentication"
            entity_type: Optional filter: "function", "class", "module", etc.
            limit: Max results (default 5, max 8).
        """
        from src.llm.embeddings import embed
        from src.storage.vector_db import search

        try:
            vector = embed(query)
        except Exception as exc:
            logger.warning("Embedding failed for query %r: %s", query, exc)
            return json.dumps({"error": f"Embedding failed: {exc}"})

        filters = {"repo_id": repository_id}
        if entity_type:
            filters["entity_type"] = entity_type

        try:
            results = search(
                collection="code_entities",
                vector=vector,
                limit=min(limit, MAX_RESULTS),
                filters=filters,
                score_threshold=0.25,
            )
        except Exception as exc:
            logger.warning("Qdrant search failed: %s", exc)
            return json.dumps({"error": f"Search failed: {exc}"})

        if not results:
            return json.dumps({"results": [], "message": "No matching entities found."})

        formatted = []
        for r in results:
            p = r.get("payload", {})
            formatted.append({
                "name": p.get("name", ""),
                "qualified_name": p.get("qualified_name", ""),
                "entity_type": p.get("entity_type", ""),
                "file_path": p.get("file_path", ""),
                "line_start": p.get("line_start"),
                "signature": p.get("signature", ""),
                "score": round(r.get("score", 0), 3),
            })

        return json.dumps({"results": formatted}, indent=2)

    return [search_code_entities]
