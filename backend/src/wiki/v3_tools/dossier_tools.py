"""Dossier query tools for V3 deep content agents.

Granular, context-aware tools that expose dossier findings, compressed
summaries, and file metadata — without raw filesystem access.
Each tool returns bounded output to avoid context explosion.
"""

import json
import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

MAX_RESULT_CHARS = 4000


def make_dossier_tools(dossier_dict: dict, compressed_dict: dict) -> list:
    """Create granular dossier + compressed query tools.

    Args:
        dossier_dict: Dossier.to_dict() — serialized dossier state.
        compressed_dict: CompressedCodebase as dict (repo_summary, file_summaries, etc.)

    Returns:
        List of LangChain tool functions.
    """
    # Pre-index responses by tag
    _by_tag: dict[str, list[dict]] = {}
    for response in dossier_dict.get("responses", []):
        for t in response.get("tags", []):
            _by_tag.setdefault(t, []).append(response)
    _all_tags = sorted(_by_tag.keys())

    # Pre-index file summaries
    _file_summaries: dict[str, dict] = compressed_dict.get("file_summaries", {})
    _dir_summaries: dict[str, dict] = compressed_dict.get("directory_summaries", {})

    @tool
    def list_tags() -> str:
        """List all available dossier tags with response counts.

        Returns a JSON object mapping each tag to the number of agent findings.
        Use this first to discover what analysis data is available.
        """
        dist = {t: len(resps) for t, resps in _by_tag.items()}
        return json.dumps({"tags": dist}, indent=2)

    @tool
    def get_findings(tag: str) -> str:
        """Get agent findings for a specific dossier tag.

        Returns summaries of all agent analyses for this tag.
        Each finding includes the agent name, confidence, and key output fields.

        Args:
            tag: Dossier tag (e.g. "architecture", "security", "api-surface",
                 "dependencies", "data-flow", "patterns", "testing").
        """
        matches = _by_tag.get(tag.strip(), [])
        if not matches:
            partial = [t for t in _all_tags if tag.lower() in t.lower()]
            return json.dumps({"tag_not_found": tag, "similar": partial[:5]})

        results = []
        total_chars = 0
        for resp in matches:
            output = resp.get("output", {})
            # Compact: take summary or first meaningful value
            compact = _compact_output(output)
            entry = {
                "agent": resp.get("agent_name", ""),
                "confidence": resp.get("confidence", 1.0),
                "findings": compact,
            }
            entry_str = json.dumps(entry)
            if total_chars + len(entry_str) > MAX_RESULT_CHARS:
                results.append({"note": f"... {len(matches) - len(results)} more findings truncated"})
                break
            results.append(entry)
            total_chars += len(entry_str)

        return json.dumps(results, indent=2)

    @tool
    def get_finding_detail(tag: str, agent_name: str) -> str:
        """Get the full output of a specific agent's finding for a tag.

        Use after get_findings() to drill into a particular agent's analysis.

        Args:
            tag: Dossier tag name.
            agent_name: Agent name from the get_findings() result.
        """
        matches = _by_tag.get(tag.strip(), [])
        for resp in matches:
            if resp.get("agent_name", "") == agent_name:
                output_str = json.dumps(resp.get("output", {}), indent=2)
                if len(output_str) > MAX_RESULT_CHARS:
                    output_str = output_str[:MAX_RESULT_CHARS] + "\n... [truncated]"
                return output_str
        return json.dumps({"error": f"No finding from '{agent_name}' under tag '{tag}'"})

    @tool
    def get_repo_summary() -> str:
        """Get the high-level repository summary and call graph overview.

        Returns the compressed repo summary (~500 words) and call graph summary
        generated during the compression phase.
        """
        parts = []
        repo_summary = compressed_dict.get("repo_summary", "")
        if repo_summary:
            parts.append(f"## Repository Summary\n{repo_summary}")
        call_graph = compressed_dict.get("call_graph_summary", "")
        if call_graph:
            parts.append(f"## Call Graph\n{call_graph}")
        import_graph = compressed_dict.get("import_graph_summary", "")
        if import_graph:
            parts.append(f"## Import Graph\n{import_graph}")
        return "\n\n".join(parts) if parts else "No repository summary available."

    @tool
    def get_file_summary(file_path: str) -> str:
        """Get the compressed summary of a specific source file.

        Returns language, line count, summary, key entities, exports, and dependencies
        — without reading the raw source code.

        Args:
            file_path: Relative path (e.g. "src/main.py"). Pass "?list" to see all files.
        """
        if file_path.strip() == "?list":
            files = sorted(_file_summaries.keys())
            return json.dumps({"files": files[:100], "total": len(files)})

        summary = _file_summaries.get(file_path.strip())
        if summary is None:
            # Try partial match
            matches = [k for k in _file_summaries if file_path.lower() in k.lower()]
            if matches:
                return json.dumps({"file_not_found": file_path, "similar": matches[:5]})
            return json.dumps({"file_not_found": file_path})

        if isinstance(summary, dict):
            return json.dumps(summary, indent=2)
        # dataclass-like object
        return json.dumps({
            "file_path": getattr(summary, "file_path", file_path),
            "language": getattr(summary, "language", ""),
            "line_count": getattr(summary, "line_count", 0),
            "summary": getattr(summary, "summary", ""),
            "key_entities": getattr(summary, "key_entities", []),
            "exported_symbols": getattr(summary, "exported_symbols", []),
            "dependencies": getattr(summary, "dependencies", []),
        }, indent=2)

    @tool
    def get_directory_summary(dir_path: str) -> str:
        """Get the compressed summary of a directory.

        Returns file count, summary, child files, and key entities.

        Args:
            dir_path: Relative directory path (e.g. "src/agents"). Pass "?list" to see all.
        """
        if dir_path.strip() == "?list":
            dirs = sorted(_dir_summaries.keys())
            return json.dumps({"directories": dirs[:80]})

        summary = _dir_summaries.get(dir_path.strip())
        if summary is None:
            matches = [k for k in _dir_summaries if dir_path.lower() in k.lower()]
            if matches:
                return json.dumps({"dir_not_found": dir_path, "similar": matches[:5]})
            return json.dumps({"dir_not_found": dir_path})

        if isinstance(summary, dict):
            return json.dumps(summary, indent=2)
        return json.dumps({
            "dir_path": getattr(summary, "dir_path", dir_path),
            "file_count": getattr(summary, "file_count", 0),
            "summary": getattr(summary, "summary", ""),
            "child_files": getattr(summary, "child_files", []),
            "key_entities": getattr(summary, "key_entities", []),
        }, indent=2)

    @tool
    def get_key_entities() -> str:
        """Get the top-50 most important code entities in the repository.

        Returns qualified names, types, and relevance scores of the most
        significant functions, classes, and modules identified during analysis.
        """
        entities = compressed_dict.get("key_entities", [])
        result = json.dumps(entities[:50], indent=2)
        if len(result) > MAX_RESULT_CHARS:
            result = result[:MAX_RESULT_CHARS] + "\n... [truncated]"
        return result

    return [list_tags, get_findings, get_finding_detail, get_repo_summary,
            get_file_summary, get_directory_summary, get_key_entities]


def _compact_output(output: dict, max_chars: int = 600) -> dict:
    """Extract the most useful fields from an agent output dict."""
    compact = {}
    # Prefer known summary fields
    for key in ("summary", "description", "overview", "analysis"):
        if key in output and isinstance(output[key], str):
            compact[key] = output[key][:max_chars]
            return compact

    # Fall back to first few string/list values
    chars = 0
    for k, v in output.items():
        if isinstance(v, str) and v.strip():
            compact[k] = v[:300]
            chars += len(compact[k])
        elif isinstance(v, list) and v:
            compact[k] = v[:5]
            chars += 100
        elif isinstance(v, dict):
            compact[k] = str(v)[:200]
            chars += 200
        if chars >= max_chars:
            break
    return compact
