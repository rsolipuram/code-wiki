"""TABULATOR agent — generates curated summary tables.

Produces LLM-curated tables with meaningful role descriptions,
replacing the mechanical table dumps from table_generator.py.
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.llm.client import chat
from src.wiki.agents.graph import report_agent_progress
from src.wiki.agents.state import WikiState

logger = logging.getLogger(__name__)

TABULATOR_SYSTEM_PROMPT = """You are a documentation specialist creating summary tables for technical wikis.

Generate clear, useful summary tables that help developers understand component roles.

RULES:
1. Include 5-15 most important components per table
2. Write a 1-sentence ROLE description (what it does and WHY), not the function signature
3. Include: Name, Type, Role, Key Dependencies
4. Sort by importance (most critical components first)
5. Use human-readable names

Output JSON array:
[
  {
    "headers": ["Name", "Type", "Role", "Dependencies"],
    "rows": [
      ["ComponentName", "class", "Handles request routing and dispatches to appropriate handlers", "Router, Config"],
      ["helperFunc", "function", "Validates input parameters before processing", "Validator"]
    ],
    "caption": "Core components of the request handling system"
  }
]"""


def tabulator_node(state: WikiState) -> dict:
    """TABULATOR node — generate tables for all sections in parallel."""
    t0 = time.monotonic()
    logger.info("TABULATOR agent starting")
    report_agent_progress("tabulator", "running", "Building summary tables")

    plan = state.get("plan", {})
    entity_index = state.get("entity_index", {})
    call_graph = state.get("call_graph", {})
    reverse_call_graph = state.get("reverse_call_graph", {})

    sections = plan.get("sections", [])
    section_tables = {}

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {}
        for section in sections:
            section_id = section.get("id", "")
            future = pool.submit(
                _generate_section_tables,
                section, entity_index, call_graph, reverse_call_graph,
            )
            futures[future] = section_id

        for future in as_completed(futures):
            section_id = futures[future]
            try:
                tables = future.result(timeout=120)
                section_tables[section_id] = tables
            except Exception as exc:
                logger.error("TABULATOR: section '%s' failed: %s", section_id, exc)
                section_tables[section_id] = []

    elapsed = time.monotonic() - t0
    total_tables = sum(len(t) for t in section_tables.values())
    logger.info(
        "TABULATOR agent complete: %d tables across %d sections (%.1fs)",
        total_tables, len(section_tables), elapsed,
    )
    report_agent_progress("tabulator", "complete", f"{total_tables} tables generated")

    return {
        "section_tables": section_tables,
        "agent_results": [{
            "agent": "tabulator",
            "success": True,
            "elapsed": elapsed,
            "total_tables": total_tables,
        }],
    }


def _generate_section_tables(
    section: dict,
    entity_index: dict,
    call_graph: dict,
    reverse_call_graph: dict,
) -> list[dict]:
    """Generate tables for a section."""
    section_title = section.get("title", "")
    table_type = section.get("table_type", "none")

    if table_type == "none":
        return []

    # Gather section files
    section_files = set()
    for sub in section.get("subsections", []):
        section_files.update(sub.get("relevant_files", []))
    for f in section.get("_all_files", []):
        section_files.add(f)

    if not section_files:
        return []

    # Gather entities for this section
    section_entities = []
    for qname, info in entity_index.items():
        if info.get("file_path") in section_files:
            # Calculate importance (callers count)
            callers = len(reverse_call_graph.get(qname, []))
            callees = len(call_graph.get(qname, []))
            section_entities.append({
                "name": info.get("name", qname.rsplit(".", 1)[-1]),
                "qname": qname,
                "type": info.get("entity_type", ""),
                "file": info.get("file_path", ""),
                "signature": info.get("signature", "")[:150],
                "callers": callers,
                "callees": callees,
            })

    if not section_entities:
        return []

    # Sort by importance (callers + callees)
    section_entities.sort(key=lambda e: e["callers"] + e["callees"], reverse=True)

    # Build entity context for LLM
    entity_text = "\n".join(
        f"  - {e['name']} ({e['type']}): {e['signature'] or e['qname']}"
        f" [called by {e['callers']}, calls {e['callees']}]"
        for e in section_entities[:30]
    )

    prompt = f"""Create a summary table for the "{section_title}" section.
Table type: {table_type}

Entities in this section:
{entity_text}

Create a table with the 10-15 most important components.
Write meaningful ROLE descriptions (not signatures).
Output ONLY a JSON array of table objects."""

    try:
        response = chat(
            [
                {"role": "system", "content": TABULATOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2048,
            temperature=0.2,
            cache_ttl=3600,
        ).strip()

        tables = _parse_tables_response(response)
        return tables[:2]  # Max 2 tables per section

    except Exception as exc:
        logger.error("TABULATOR: LLM call failed for '%s': %s", section_title, exc)
        # Fallback: generate a basic table from entity metadata
        return [_fallback_table(section_title, section_entities)]


def _parse_tables_response(response: str) -> list[dict]:
    """Parse LLM response into list of table dicts."""
    text = response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [t for t in data if "headers" in t and "rows" in t]
        if isinstance(data, dict) and "headers" in data:
            return [data]
        return []
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", text)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, list):
                    return [t for t in data if "headers" in t and "rows" in t]
            except json.JSONDecodeError:
                pass
        return []


def _fallback_table(section_title: str, entities: list[dict]) -> dict:
    """Generate a basic table when LLM fails."""
    rows = []
    for e in entities[:15]:
        deps = []
        name = e.get("name", "")
        etype = e.get("type", "")
        sig = e.get("signature", "")

        # Basic role description from signature
        if "class" in etype:
            role = f"Class defined in {e.get('file', '').rsplit('/', 1)[-1]}"
        elif sig:
            role = sig[:80]
        else:
            role = f"{etype.title()} in {e.get('file', '').rsplit('/', 1)[-1]}"

        rows.append([name, etype, role, ""])

    return {
        "headers": ["Name", "Type", "Role", "Dependencies"],
        "rows": rows,
        "caption": f"Components in {section_title}",
    }
