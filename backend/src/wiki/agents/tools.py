"""Domain-specific tool primitives for wiki agents.

All tools are read-only (no side effects) and safe for parallel execution.
Tools access state via closure — created by make_tools() which captures
the WikiState values.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def make_tools(
    repo_path: str,
    entity_index: dict,
    call_graph: dict,
    reverse_call_graph: dict,
    name_to_qname: dict,
) -> list:
    """Create agent tools that close over the wiki state.

    Returns a list of LangChain tool functions.
    """

    @tool
    def query_call_graph(
        entity_qname: str,
        direction: str = "callees",
        depth: int = 1,
    ) -> str:
        """Traverse the code call graph to find entity relationships.

        Args:
            entity_qname: Qualified name of the entity (e.g., 'module.ClassName.method').
            direction: 'callees' (what it calls), 'callers' (what calls it), or 'both'.
            depth: How many hops to traverse (1-3).

        Returns:
            JSON list of related entities with their types and distances.
        """
        depth = min(max(depth, 1), 3)
        results: list[dict] = []
        visited: set[str] = set()

        def _traverse(qname: str, current_depth: int, graph: dict) -> None:
            if current_depth > depth or qname in visited:
                return
            visited.add(qname)
            for target in graph.get(qname, []):
                if target in visited:
                    continue
                info = entity_index.get(target, {})
                results.append({
                    "qname": target,
                    "entity_type": info.get("entity_type", "unknown"),
                    "file_path": info.get("file_path", ""),
                    "distance": current_depth,
                })
                if current_depth < depth:
                    _traverse(target, current_depth + 1, graph)

        if direction in ("callees", "both"):
            _traverse(entity_qname, 1, call_graph)
        if direction in ("callers", "both"):
            visited.clear()
            _traverse(entity_qname, 1, reverse_call_graph)

        return json.dumps(results[:50], indent=2)

    @tool
    def rag_search(query: str, file_filter: str = "") -> str:
        """Semantic search against indexed code entities and dossier findings.

        Args:
            query: Natural language search query.
            file_filter: Optional file path prefix to filter results.

        Returns:
            JSON list of matching entities with scores.
        """
        # Search by matching against entity index metadata
        results: list[dict] = []
        query_lower = query.lower()
        query_words = set(query_lower.split())

        for qname, info in entity_index.items():
            score = 0.0
            name = info.get("name", "").lower()
            file_path = info.get("file_path", "")

            if file_filter and not file_path.startswith(file_filter):
                continue

            # Name match scoring
            if query_lower in name:
                score += 0.8
            elif any(w in name for w in query_words):
                score += 0.4

            # Qualified name match
            qname_lower = qname.lower()
            if any(w in qname_lower for w in query_words):
                score += 0.3

            # File path match
            if any(w in file_path.lower() for w in query_words):
                score += 0.2

            if score > 0:
                results.append({
                    "qname": qname,
                    "name": info.get("name", ""),
                    "entity_type": info.get("entity_type", ""),
                    "file_path": file_path,
                    "signature": info.get("signature", "")[:200],
                    "score": round(score, 2),
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return json.dumps(results[:20], indent=2)

    @tool
    def read_source(
        file_path: str,
        start_line: int = 0,
        end_line: int = 0,
    ) -> str:
        """Read source code from the repository.

        Args:
            file_path: Relative path within the repository.
            start_line: First line to read (1-indexed, 0 = beginning).
            end_line: Last line to read (0 = read up to 200 lines from start).

        Returns:
            File contents (max 200 lines).
        """
        full_path = Path(repo_path) / file_path
        if not full_path.is_file():
            return f"File not found: {file_path}"

        try:
            lines = full_path.read_text(errors="replace").splitlines()
        except Exception as exc:
            return f"Error reading {file_path}: {exc}"

        if start_line > 0:
            start_idx = max(0, start_line - 1)
        else:
            start_idx = 0

        if end_line > 0:
            end_idx = min(end_line, len(lines))
        else:
            end_idx = min(start_idx + 200, len(lines))

        selected = lines[start_idx:end_idx]
        numbered = [
            f"{start_idx + i + 1:4d} | {line}"
            for i, line in enumerate(selected)
        ]
        return "\n".join(numbered)

    return [query_call_graph, rag_search, read_source]
