"""V4 Code Embedder — retrieval-first code extraction.

Takes code placeholder specs from the Writer and retrieves real source code
from the repository using Qdrant vector search and file tools.
Minimal LLM usage — primarily a retrieval agent.
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _detect_language(file_path: str) -> str:
    """Infer language from file extension."""
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".tsx": "typescript", ".jsx": "javascript", ".java": "java",
        ".go": "go", ".rs": "rust", ".rb": "ruby", ".cpp": "cpp",
        ".c": "c", ".cs": "csharp", ".swift": "swift", ".kt": "kotlin",
        ".sh": "bash", ".yaml": "yaml", ".yml": "yaml", ".json": "json",
        ".toml": "toml", ".sql": "sql", ".html": "html", ".css": "css",
        ".md": "markdown",
    }
    suffix = Path(file_path).suffix.lower()
    return ext_map.get(suffix, "text")


def _read_file_lines(
    repo_path: str,
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    max_lines: int = 40,
) -> Optional[dict]:
    """Read source code from the repo, returning code + metadata.

    Returns dict with: code, language, file_path, start_line, end_line, validated
    Or None if file not found.
    """
    full_path = Path(repo_path) / file_path
    if not full_path.is_file():
        return None

    try:
        content = full_path.read_text(errors="replace")
    except Exception:
        return None

    lines = content.splitlines()
    total = len(lines)

    if start_line is not None:
        start = max(1, start_line)
        end = min(total, end_line or (start + max_lines - 1))
        # Clamp to max_lines
        if end - start + 1 > max_lines:
            end = start + max_lines - 1
        selected = lines[start - 1:end]
        return {
            "code": "\n".join(selected),
            "language": _detect_language(file_path),
            "file_path": file_path,
            "start_line": start,
            "end_line": end,
            "validated": True,
        }

    # No line range — return first max_lines (or whole file if short)
    selected = lines[:max_lines]
    return {
        "code": "\n".join(selected),
        "language": _detect_language(file_path),
        "file_path": file_path,
        "start_line": 1,
        "end_line": len(selected),
        "validated": True,
    }


def _parse_line_range(lines_str: str) -> tuple[Optional[int], Optional[int]]:
    """Parse '10-35' into (10, 35). Returns (None, None) on failure."""
    m = re.match(r'(\d+)\s*-\s*(\d+)', lines_str)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r'(\d+)', lines_str)
    if m:
        return int(m.group(1)), None
    return None, None


def _search_qdrant_for_symbol(
    query: str,
    repository_id: str,
    entity_type: Optional[str] = None,
) -> Optional[dict]:
    """Search Qdrant for a code entity, return best match payload."""
    try:
        from src.llm.embeddings import embed
        from src.storage.vector_db import search
    except ImportError:
        logger.warning("Qdrant/embeddings not available")
        return None

    try:
        vector = embed(query)
        filters = {"repo_id": repository_id}
        if entity_type:
            filters["entity_type"] = entity_type

        results = search(
            collection="code_entities",
            vector=vector,
            limit=3,
            filters=filters,
            score_threshold=0.25,
        )
        if results:
            return results[0].get("payload", {})
    except Exception as exc:
        logger.warning("Qdrant search failed for %r: %s", query, exc)

    return None


def _grep_for_symbol(repo_path: str, symbol: str) -> Optional[dict]:
    """Fallback: grep for a symbol definition in the repo."""
    import subprocess

    # Try common definition patterns
    patterns = [
        f"(def|class|function|const|let|var)\\s+{re.escape(symbol)}",
        f"{re.escape(symbol)}\\s*=",
        f"{re.escape(symbol)}\\s*\\(",
    ]

    for pattern in patterns:
        try:
            result = subprocess.run(
                ["grep", "-rn", "-E", pattern, repo_path,
                 "--include=*.py", "--include=*.ts", "--include=*.js",
                 "--include=*.tsx", "--include=*.java", "--include=*.go"],
                capture_output=True, text=True, timeout=10,
            )
            if result.stdout.strip():
                first_line = result.stdout.strip().split("\n")[0]
                # Parse grep output: file:line:content
                parts = first_line.split(":", 2)
                if len(parts) >= 2:
                    file_path = parts[0]
                    line_num = int(parts[1])
                    # Make relative to repo_path
                    rel_path = str(Path(file_path).relative_to(repo_path))
                    return {"file_path": rel_path, "line_start": line_num}
        except Exception:
            continue

    return None


def _resolve_one_spec(
    spec: dict,
    repo_path: str,
    repository_id: str,
) -> dict:
    """Resolve a single code placeholder spec into actual source code.

    Priority:
    1. file + lines → read_file directly
    2. symbol → Qdrant → read_file
    3. context → Qdrant semantic search → read_file
    4. Failure → return empty result
    """
    tag_index = spec.get("tag_index", 0)
    file_path = spec.get("file", "")
    lines_str = spec.get("lines", "")
    symbol = spec.get("symbol", "")
    context = spec.get("context", "")
    lang = spec.get("lang", "")

    base_result = {
        "tag_index": tag_index,
        "code": "",
        "language": lang or "text",
        "file_path": "",
        "start_line": None,
        "end_line": None,
        "validated": False,
    }

    # Strategy 1: Direct file + lines
    if file_path and lines_str:
        start, end = _parse_line_range(lines_str)
        result = _read_file_lines(repo_path, file_path, start, end)
        if result:
            if lang:
                result["language"] = lang
            return {**base_result, **result, "tag_index": tag_index}

    # Strategy 1b: Direct file (no lines) — read around symbol or from top
    if file_path and not lines_str:
        # If we have a symbol, try to find it in the file
        if symbol:
            full_path = Path(repo_path) / file_path
            if full_path.is_file():
                try:
                    content = full_path.read_text(errors="replace")
                    for i, line in enumerate(content.splitlines(), 1):
                        if symbol in line:
                            result = _read_file_lines(repo_path, file_path, max(1, i - 2), i + 37)
                            if result:
                                return {**base_result, **result, "tag_index": tag_index}
                except Exception:
                    pass

        # Fallback: read from top of file
        result = _read_file_lines(repo_path, file_path)
        if result:
            if lang:
                result["language"] = lang
            return {**base_result, **result, "tag_index": tag_index}

    # Strategy 2: Symbol → Qdrant → read_file
    if symbol:
        payload = _search_qdrant_for_symbol(symbol, repository_id)
        if payload:
            found_file = payload.get("file_path", "")
            found_line = payload.get("line_start")
            if found_file:
                start = max(1, (found_line or 1) - 2)
                result = _read_file_lines(repo_path, found_file, start, start + 39)
                if result:
                    return {**base_result, **result, "tag_index": tag_index}

        # Qdrant miss — try grep
        grep_result = _grep_for_symbol(repo_path, symbol)
        if grep_result:
            found_file = grep_result["file_path"]
            found_line = grep_result["line_start"]
            start = max(1, found_line - 2)
            result = _read_file_lines(repo_path, found_file, start, start + 39)
            if result:
                return {**base_result, **result, "tag_index": tag_index}

    # Strategy 3: Context → Qdrant semantic search
    if context:
        payload = _search_qdrant_for_symbol(context, repository_id)
        if payload:
            found_file = payload.get("file_path", "")
            found_line = payload.get("line_start")
            if found_file:
                start = max(1, (found_line or 1) - 2)
                result = _read_file_lines(repo_path, found_file, start, start + 39)
                if result:
                    return {**base_result, **result, "tag_index": tag_index}

    logger.warning(
        "Code embedder: could not resolve spec tag_index=%d (file=%r, symbol=%r)",
        tag_index, file_path, symbol,
    )
    return base_result


def v4_code_embedder_node(state: dict) -> dict:
    """LangGraph node: retrieve real source code for all code placeholders."""
    code_specs = state.get("code_specs") or []
    if not code_specs:
        return {"code_results": []}

    repo_path = state.get("repo_path", "")
    repository_id = state.get("repository_id", "")

    t0 = time.monotonic()
    results = [
        _resolve_one_spec(spec, repo_path, repository_id)
        for spec in code_specs
    ]
    elapsed = time.monotonic() - t0

    resolved_count = sum(1 for r in results if r.get("validated"))
    logger.info(
        "Code embedder: %d/%d resolved, %.1fs",
        resolved_count, len(results), elapsed,
    )

    return {"code_results": results}
