"""Structured table generation — file-based entity lookup.

Decoupled from narrator-produced entities_referenced. Uses
section_plan.all_relevant_files to deterministically find entities
and build component/API/tools tables.
"""

import logging

from src.parsers.base import ParsedEntity

logger = logging.getLogger(__name__)


def generate_table(
    section_files: list[str],
    entities: list[ParsedEntity],
    entity_index: dict[str, dict],
    reverse_call_graph: dict[str, list[str]],
    table_type: str,
    max_rows: int = 30,
    repo_path: str = "",
) -> list[dict]:
    """Generate structured table using file-based entity lookup.

    Returns list of [{headers, rows}].
    """
    section_entities = _collect_section_entities(section_files, entities, entity_index)
    if not section_entities:
        return []

    if table_type == "components":
        return _build_components_table(section_entities, entity_index, max_rows)
    elif table_type == "apis":
        return _build_apis_table(section_entities, entity_index, max_rows)
    elif table_type == "tools":
        return _build_tools_table(section_entities, entity_index, reverse_call_graph, max_rows)

    return []


def _collect_section_entities(
    section_files: list[str],
    entities: list[ParsedEntity],
    entity_index: dict[str, dict],
) -> list[ParsedEntity]:
    """Filter entities to those whose file_path is in section_files."""
    file_set = set(section_files)
    result: list[ParsedEntity] = []
    seen: set[str] = set()

    for e in entities:
        if e.entity_type == "module" or e.name.startswith("_"):
            continue
        if e.qualified_name in seen:
            continue

        # Check if entity's file is in the section
        info = entity_index.get(e.qualified_name)
        file_path = info.get("file_path", e.file_path) if info else e.file_path
        if file_path in file_set:
            result.append(e)
            seen.add(e.qualified_name)

    return result


def _get_entity_file(e: ParsedEntity, entity_index: dict[str, dict]) -> str:
    """Get normalized file_path from entity_index, falling back to entity's own path."""
    info = entity_index.get(e.qualified_name)
    if info:
        return info.get("file_path", e.file_path)
    return e.file_path


def _build_components_table(
    section_entities: list[ParsedEntity],
    entity_index: dict[str, dict],
    max_rows: int,
) -> list[dict]:
    """Build Name/Type/File/Description table."""
    headers = ["Name", "Type", "File", "Description"]
    rows = []
    for e in section_entities[:max_rows]:
        desc = (e.docstring or "")[:100] if e.docstring else (e.signature or "")[:80]
        rows.append([e.name, e.entity_type, _get_entity_file(e, entity_index), desc])
    if rows:
        return [{"headers": headers, "rows": rows}]
    return []


def _build_apis_table(
    section_entities: list[ParsedEntity],
    entity_index: dict[str, dict],
    max_rows: int,
) -> list[dict]:
    """Build Endpoint/Type/File/Description table."""
    headers = ["Endpoint", "Type", "File", "Description"]
    rows = []
    for e in section_entities[:max_rows]:
        desc = (e.docstring or e.signature or "")[:100]
        rows.append([e.name, e.entity_type, _get_entity_file(e, entity_index), desc])
    if rows:
        return [{"headers": headers, "rows": rows}]
    return []


def _build_tools_table(
    section_entities: list[ParsedEntity],
    entity_index: dict[str, dict],
    reverse_call_graph: dict[str, list[str]],
    max_rows: int,
) -> list[dict]:
    """Build Name/Purpose/Used By table using the reverse call graph."""
    headers = ["Name", "Purpose", "Used By"]
    rows = []
    for e in section_entities[:max_rows]:
        callers = reverse_call_graph.get(e.qualified_name, [])
        caller_names = [
            entity_index.get(qn, {}).get("name", qn.rsplit(".", 1)[-1])
            for qn in callers[:3]
        ]
        desc = (e.docstring or "")[:80] if e.docstring else ""
        rows.append([e.name, desc, ", ".join(caller_names) or "—"])
    if rows:
        return [{"headers": headers, "rows": rows}]
    return []
