"""Wiki context builder — retrieves relevant Dossier findings via Qdrant RAG
and combines with direct source code for a given module.
"""

import logging
from pathlib import Path
from typing import Any

from src.dossier.rag_index import search_dossier

logger = logging.getLogger(__name__)

# Maximum characters of source code to include in LLM context
_MAX_SOURCE_CHARS = 8000
# Maximum Dossier findings to include per module
_MAX_DOSSIER_RESULTS = 8


def build_module_context(
    module_name: str,
    file_paths: list[str],
    repository_id: str,
    repo_path: str,
) -> dict[str, Any]:
    """Retrieve and combine Dossier findings + source code for a module.

    Args:
        module_name: Human-readable module name.
        file_paths: Relative file paths in this module.
        repository_id: Repository UUID for Qdrant filtering.
        repo_path: Absolute local path to the repository root.

    Returns:
        Dict with keys: source_code, dossier_findings, module_name, file_paths.
    """
    # Collect source code from module files
    source_snippets: list[str] = []
    total_chars = 0

    for rel_path in file_paths:
        if total_chars >= _MAX_SOURCE_CHARS:
            break
        abs_path = Path(repo_path) / rel_path
        try:
            content = abs_path.read_text(errors="replace")
            remaining = _MAX_SOURCE_CHARS - total_chars
            snippet = content[:remaining]
            source_snippets.append(f"=== {rel_path} ===\n{snippet}")
            total_chars += len(snippet)
        except OSError as exc:
            logger.debug("Cannot read %s: %s", abs_path, exc)

    # Retrieve Dossier findings via RAG
    try:
        dossier_findings = search_dossier(
            query=f"{module_name} security dependencies architecture",
            repository_id=repository_id,
            limit=_MAX_DOSSIER_RESULTS,
        )
    except Exception as exc:
        logger.warning("Dossier RAG query failed: %s", exc)
        dossier_findings = []

    return {
        "module_name": module_name,
        "file_paths": file_paths,
        "source_code": "\n\n".join(source_snippets),
        "dossier_findings": dossier_findings,
    }
