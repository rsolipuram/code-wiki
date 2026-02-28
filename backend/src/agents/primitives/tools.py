"""Capability primitives used by ReAct and single-pass agents.

Each primitive is a callable tool with typed inputs/outputs.
These are registered as LangGraph tool nodes.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

from src.dossier.manager import DossierManager
from src.dossier.schema import SecurityFinding, Severity

logger = logging.getLogger(__name__)


def read_file(file_path: str, max_lines: int = 200) -> str:
    """Read a source file and return its contents (up to max_lines).

    Args:
        file_path: Absolute or relative path to the file.
        max_lines: Maximum lines to return (avoids flooding context).

    Returns:
        File contents as string, or error message.
    """
    try:
        lines = Path(file_path).read_text(errors="replace").splitlines()
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n... [{len(lines) - max_lines} more lines truncated]"
        return "\n".join(lines)
    except OSError as exc:
        return f"ERROR: Cannot read {file_path}: {exc}"


def search_code(
    repo_path: str,
    pattern: str,
    extensions: list[str] | None = None,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """Search source files for a regex pattern.

    Args:
        repo_path: Repository root directory.
        pattern: Regex pattern to search for.
        extensions: File extensions to search (e.g. [".py", ".ts"]).
        max_results: Maximum number of matches to return.

    Returns:
        List of dicts with keys: file, line_number, line_content.
    """
    root = Path(repo_path)
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        logger.warning("Invalid regex %r: %s", pattern, exc)
        return []

    results: list[dict[str, Any]] = []
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}

    for file_path in root.rglob("*"):
        if len(results) >= max_results:
            break
        if not file_path.is_file():
            continue
        if any(skip in file_path.parts for skip in skip_dirs):
            continue
        if extensions and file_path.suffix.lower() not in extensions:
            continue
        try:
            for i, line in enumerate(file_path.read_text(errors="replace").splitlines(), 1):
                if regex.search(line):
                    results.append({
                        "file": str(file_path.relative_to(root)),
                        "line_number": i,
                        "line_content": line.strip(),
                    })
                    if len(results) >= max_results:
                        break
        except OSError:
            pass
    return results


def query_dossier(dossier_manager: DossierManager, section: str, query: Optional[str] = None) -> Any:
    """Read a section of the Dossier.

    Args:
        dossier_manager: The shared DossierManager.
        section: Section name (e.g. "security", "dependencies").
        query: Optional filter string (matched against descriptions).

    Returns:
        Section value, filtered if query provided.
    """
    value = dossier_manager.get_section(section)
    if value is None:
        return None
    if query and isinstance(value, list):
        query_lower = query.lower()
        return [
            item for item in value
            if query_lower in str(getattr(item, "description", "") or "").lower()
        ]
    return value


def write_finding(dossier_manager: DossierManager, finding: SecurityFinding) -> str:
    """Append a SecurityFinding to the Dossier.

    Args:
        dossier_manager: The shared DossierManager.
        finding: The SecurityFinding to write.

    Returns:
        "OK: <finding.id>" on success.
    """
    dossier_manager.write_security_finding(finding)
    return f"OK: {finding.id}"


def parse_ast(file_path: str) -> dict[str, Any]:
    """Return a structural summary of a Python or TypeScript file via the parser.

    Args:
        file_path: Absolute path to the source file.

    Returns:
        Dict with 'entities' list (name, type, line).
    """
    from src.parsers import get_parser
    from src.parsers.base import UnsupportedLanguageError

    ext = Path(file_path).suffix.lower()
    try:
        parser = get_parser(ext)
        entities = parser.parse_file(file_path)
        return {
            "entities": [
                {"name": e.name, "type": e.entity_type, "line": e.line_start}
                for e in entities
            ]
        }
    except UnsupportedLanguageError:
        return {"entities": [], "error": f"Unsupported extension {ext}"}
    except Exception as exc:
        return {"entities": [], "error": str(exc)}
