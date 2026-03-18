"""ASSEMBLER agent — deterministic marker resolution (no LLM).

Takes ANNOTATOR's marked-up prose and resolves all markers into
structured segments. Attaches DIAGRAMMER's diagrams and TABULATOR's
tables to produce final EnrichedSection objects.

Reuses existing marker resolution functions from enricher.py.
"""

import logging
import re
import time

from src.wiki.enricher import (
    auto_detect_entity_references,
    extract_backtick_fences,
    inject_code_blocks,
    inject_source_links,
    resolve_cross_section_links,
    resolve_heading_markers,
)
from src.wiki.v2_types import EnrichedSection, WikiPlan, WikiSectionPlan, WikiSubsection
from src.wiki.agents.graph import report_agent_progress
from src.wiki.agents.state import WikiState

logger = logging.getLogger(__name__)


def assembler_node(state: WikiState) -> dict:
    """ASSEMBLER node — resolve markers and assemble EnrichedSections."""
    t0 = time.monotonic()
    logger.info("ASSEMBLER agent starting")
    report_agent_progress("assembler", "running", "Assembling final pages")

    plan_dict = state.get("plan", {})
    annotated_sections = state.get("annotated_sections", {})
    narrated_sections = state.get("narrated_sections", {})
    section_diagrams = state.get("section_diagrams", {})
    section_tables = state.get("section_tables", {})
    entity_index = state.get("entity_index", {})
    repo_url = state.get("repo_url", "")
    commit_hash = state.get("commit_hash", "")
    repo_path = state.get("repo_path", "")

    # Build name→qname lookup
    name_to_qname: dict[str, str] = {}
    for qname, info in entity_index.items():
        short = info.get("name", qname.rsplit(".", 1)[-1])
        if short not in name_to_qname:
            name_to_qname[short] = qname

    # Reconstruct WikiPlan for cross-section link resolution
    wiki_plan = _reconstruct_plan(plan_dict)

    enriched_sections: list[dict] = []

    for section_plan_dict in plan_dict.get("sections", []):
        section_id = section_plan_dict.get("id", "")
        section_title = section_plan_dict.get("title", section_id)

        # Get annotated prose (fall back to narrated prose)
        prose = annotated_sections.get(section_id, "")
        if not prose:
            narrated = narrated_sections.get(section_id, {})
            prose = narrated.get("prose", "") if isinstance(narrated, dict) else ""

        if not prose:
            logger.warning("ASSEMBLER: no prose for section '%s'", section_id)
            continue

        # Get subsections from narrated section
        narrated = narrated_sections.get(section_id, {})
        subsections_raw = narrated.get("subsections", []) if isinstance(narrated, dict) else []

        # Get section plan subsections for file context
        plan_subsections = section_plan_dict.get("subsections", [])
        if not subsections_raw:
            subsections_raw = plan_subsections

        # Collect section files for diagram fallback
        section_files = []
        for sub in (subsections_raw or plan_subsections):
            if isinstance(sub, dict):
                section_files.extend(sub.get("relevant_files", []))

        diagrams = section_diagrams.get(section_id, [])

        # Resolve markers using enricher functions
        try:
            enriched = _assemble_section(
                section_id=section_id,
                title=section_title,
                prose=prose,
                entity_index=entity_index,
                name_to_qname=name_to_qname,
                repo_url=repo_url,
                commit_hash=commit_hash,
                repo_path=repo_path,
                wiki_plan=wiki_plan,
                diagrams=diagrams,
                tables=section_tables.get(section_id, []),
                subsections_raw=subsections_raw if subsections_raw else plan_subsections,
            )
            enriched_sections.append(enriched)
        except Exception as exc:
            logger.error("ASSEMBLER: failed for section '%s': %s", section_id, exc)

    elapsed = time.monotonic() - t0
    total_words = sum(s.get("word_count", 0) for s in enriched_sections)
    total_links = sum(len(s.get("source_links", [])) for s in enriched_sections)
    n_sections = len(enriched_sections)
    logger.info(
        "ASSEMBLER agent complete: %d sections, %d words, %d source links (%.1fs)",
        n_sections, total_words, total_links, elapsed,
    )
    report_agent_progress("assembler", "complete", f"{n_sections} sections assembled")

    return {
        "enriched_sections": enriched_sections,
        "agent_results": [{
            "agent": "assembler",
            "success": True,
            "elapsed": elapsed,
            "sections": len(enriched_sections),
            "total_words": total_words,
            "total_links": total_links,
        }],
    }


def _assemble_section(
    section_id: str,
    title: str,
    prose: str,
    entity_index: dict,
    name_to_qname: dict,
    repo_url: str,
    commit_hash: str,
    repo_path: str,
    wiki_plan: WikiPlan,
    diagrams: list[dict],
    tables: list[dict],
    subsections_raw: list[dict],
) -> dict:
    """Assemble a single EnrichedSection from annotated prose + diagrams + tables."""

    # 1. Resolve [[entity:...]] markers → source_link segments
    segments, source_links = inject_source_links(
        prose, entity_index, name_to_qname, repo_url, commit_hash,
    )

    # 2. Resolve [[code:...]] markers → code_block segments
    segments, code_blocks = inject_code_blocks(segments, repo_path)

    # 3. Convert backtick fences (in case LLM used them despite prompt)
    segments = extract_backtick_fences(segments)

    # 4. Resolve [[section:...]] markers → section_link segments
    segments = resolve_cross_section_links(segments, wiki_plan)

    # 5. Resolve [[heading:...]] markers → heading segments
    segments = resolve_heading_markers(segments)

    # 5b. Auto-detect entity references in prose text (word-boundary matching)
    segments, auto_links = auto_detect_entity_references(
        segments, entity_index, name_to_qname, repo_url, commit_hash,
    )
    source_links.extend(auto_links)

    # 6. Build subsections list
    subsections = [
        {"id": sub.get("id", ""), "title": sub.get("title", ""), "anchor": sub.get("id", "")}
        for sub in subsections_raw
    ]

    # 7. Count words in text segments
    word_count = sum(
        len(seg.get("content", "").split())
        for seg in segments
        if seg.get("type") == "text"
    )

    # 8. Extract key_components from entity_index for this section
    section_files = set()
    for sub in subsections_raw:
        section_files.update(sub.get("relevant_files", []) if isinstance(sub, dict) else [])

    key_components = []
    for qname, info in entity_index.items():
        if info.get("file_path") in section_files and info.get("entity_type") in ("class", "function"):
            name = info.get("name", qname.rsplit(".", 1)[-1])
            if not name.startswith("_"):
                key_components.append({
                    "name": name,
                    "type": info.get("entity_type", ""),
                    "qualified_name": qname,
                    "file_path": info.get("file_path", ""),
                    "signature": info.get("signature", ""),
                })
    # Sort by type (classes first) then name
    key_components.sort(key=lambda c: (0 if c["type"] == "class" else 1, c["name"]))
    key_components = key_components[:30]

    # 9. Extract dependencies from source_links (cross-section references)
    internal_deps = set()
    external_deps = set()
    for link in source_links:
        target_file = link.get("file_path", "")
        if target_file and target_file not in section_files:
            internal_deps.add(target_file.rsplit("/", 1)[0] if "/" in target_file else target_file)

    # 10. Extract related pages from cross-section links in segments
    related_pages = []
    for seg in segments:
        s_type = seg.get("type") if isinstance(seg, dict) else getattr(seg, "type", None)
        if s_type == "section_link":
            target = seg.get("target") if isinstance(seg, dict) else getattr(seg, "target", "")
            text = seg.get("text") if isinstance(seg, dict) else getattr(seg, "text", "")
            if target:
                related_pages.append({"slug": target, "title": text or target})

    # 11. Interleave diagrams into prose segments
    final_segments = _interleave_diagrams(segments, diagrams)
    
    # 12. Interleave tables into prose segments
    final_segments = _interleave_tables(final_segments, tables)

    return {
        "section_id": section_id,
        "title": title,
        "prose_segments": final_segments,
        "diagrams": diagrams,  # Keep original list for safety
        "tables": tables,
        "source_links": source_links,
        "code_blocks": code_blocks,
        "subsections": subsections,
        "word_count": word_count,
        "key_components": key_components,
        "internal_deps": sorted(internal_deps),
        "related_pages": related_pages,
    }


def _interleave_diagrams(segments: list[dict], diagrams: list[dict]) -> list[dict]:
    """Insert diagrams into the segments list at logical break points."""
    if not diagrams:
        return segments

    result = []
    diagram_queue = list(diagrams)
    heading_count = 0
    text_segment_count = 0

    for seg in segments:
        result.append(seg)
        # Check if this is a heading segment
        seg_type = seg.get("type") if isinstance(seg, dict) else getattr(seg, "type", None)
        
        if seg_type == "heading":
            heading_count += 1
            # Insert a diagram after every 2nd heading (starting from the 1st)
            if diagram_queue and (heading_count % 2 == 1):
                diag = diagram_queue.pop(0)
                result.append({
                    "type": "diagram",
                    "mermaid_source": diag.get("mermaid_source", ""),
                    "caption": diag.get("caption", ""),
                })
        elif seg_type == "text":
            text_segment_count += 1
            # Fallback: If no headings but many text segments, insert after every 5th text segment
            if diagram_queue and heading_count == 0 and text_segment_count % 5 == 0:
                diag = diagram_queue.pop(0)
                result.append({
                    "type": "diagram",
                    "mermaid_source": diag.get("mermaid_source", ""),
                    "caption": diag.get("caption", ""),
                })

    # Append any remaining diagrams at the end
    for diag in diagram_queue:
        result.append({
            "type": "diagram",
            "mermaid_source": diag.get("mermaid_source", ""),
            "caption": diag.get("caption", ""),
        })

    return result


def _interleave_tables(segments: list[dict], tables: list[dict]) -> list[dict]:
    """Insert tables into the segments list at logical break points."""
    if not tables:
        return segments

    result = []
    table_queue = list(tables)
    heading_count = 0
    text_segment_count = 0

    for seg in segments:
        result.append(seg)
        seg_type = seg.get("type")
        
        if seg_type == "heading":
            heading_count += 1
            # Insert a table after every 3rd heading (starting from the 2nd)
            if table_queue and (heading_count % 3 == 2):
                tbl = table_queue.pop(0)
                result.append({
                    "type": "table",
                    "headers": tbl.get("headers", []),
                    "rows": tbl.get("rows", []),
                    "caption": tbl.get("caption", ""),
                })
        elif seg_type == "text":
            text_segment_count += 1
            # Fallback: if many text segments and few headings, insert after every 8th text segment
            if table_queue and heading_count < 2 and text_segment_count % 8 == 0:
                tbl = table_queue.pop(0)
                result.append({
                    "type": "table",
                    "headers": tbl.get("headers", []),
                    "rows": tbl.get("rows", []),
                    "caption": tbl.get("caption", ""),
                })

    # Append remaining
    for tbl in table_queue:
        result.append({
            "type": "table",
            "headers": tbl.get("headers", []),
            "rows": tbl.get("rows", []),
            "caption": tbl.get("caption", ""),
        })

    return result


def _reconstruct_plan(plan_dict: dict) -> WikiPlan:
    """Reconstruct a WikiPlan object from the state dict for enricher functions."""
    sections = []
    for s in plan_dict.get("sections", []):
        subsections = []
        for sub in s.get("subsections", []):
            subsections.append(WikiSubsection(
                id=sub.get("id", ""),
                title=sub.get("title", ""),
                relevant_files=sub.get("relevant_files", []),
                relevant_entities=sub.get("relevant_entities", []),
                describes=sub.get("describes", ""),
            ))
        sections.append(WikiSectionPlan(
            id=s.get("id", ""),
            title=s.get("title", ""),
            subsections=subsections,
            diagram_type=s.get("diagram_type", "none"),
            table_type=s.get("table_type", "none"),
        ))

    return WikiPlan(
        title=plan_dict.get("title", ""),
        sections=sections,
        total_files_covered=plan_dict.get("total_files_covered", 0),
        uncovered_files=plan_dict.get("uncovered_files", []),
    )
