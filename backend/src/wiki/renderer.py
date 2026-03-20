"""Phase 4: Final page assembly.

Converts enriched sections into the V2 content schema (dict)
that gets stored as JSONB in WikiPage.content.

Adaptive rendering:
  - <10k words total → single page with inline sections
  - >=10k words → multi-page with separate WikiPage per section
"""

import logging
from typing import Any

from src.wiki.v2_types import EnrichedSection, WikiPlan

logger = logging.getLogger(__name__)


def render_wiki_pages(
    plan: WikiPlan,
    system_narrative: str,
    enriched_sections: list[EnrichedSection],
    repo_name: str,
    repo_url: str,
    fingerprint,
    commit_hash: str,
    overview_diagram: dict | None = None,
) -> list[dict[str, Any]]:
    """Render final wiki pages from enriched sections.

    Returns list of dicts, each containing {slug, title, page_type, content}.
    """
    total_words = sum(s.word_count for s in enriched_sections)
    logger.info(
        "Rendering %d sections (%d total words)",
        len(enriched_sections), total_words,
    )

    # Multi-page if 3+ sections — single page only for very small wikis
    if total_words < 2000 and len(enriched_sections) <= 2:
        logger.info("Rendering single page (small wiki: %d words, %d sections)", total_words, len(enriched_sections))
        return [_render_single_page(
            plan, system_narrative, enriched_sections,
            repo_name, repo_url, fingerprint, commit_hash,
            overview_diagram=overview_diagram,
        )]
    else:
        logger.info("Rendering multi-page (%d sections)", len(enriched_sections))
        return _render_multi_page(
            plan, system_narrative, enriched_sections,
            repo_name, repo_url, fingerprint, commit_hash,
            overview_diagram=overview_diagram,
        )


def _render_single_page(
    plan: WikiPlan,
    system_narrative: str,
    enriched_sections: list[EnrichedSection],
    repo_name: str,
    repo_url: str,
    fingerprint,
    commit_hash: str,
    overview_diagram: dict | None = None,
) -> dict[str, Any]:
    """Render everything into a single home page with inline sections."""
    system_context_diagram = _build_system_context_diagram(repo_name, repo_url, fingerprint)
    # Concatenate all prose_segments with heading separators
    all_segments: list[dict] = []
    all_diagrams: list[dict] = []
    all_tables: list[dict] = []
    all_source_links: list[dict] = []
    all_code_blocks: list[dict] = []
    all_subsections: list[dict] = []

    # Include C4 context/overview diagrams if available
    if system_context_diagram:
        all_diagrams.append(system_context_diagram)
    if overview_diagram:
        all_diagrams.append(overview_diagram)

    for section in enriched_sections:
        # Add section heading
        all_segments.append({
            "type": "heading",
            "level": 2,
            "text": section.title,
        })
        all_segments.extend(section.prose_segments)
        all_diagrams.extend(section.diagrams)
        all_tables.extend(section.tables)
        all_source_links.extend(section.source_links)
        all_code_blocks.extend(section.code_blocks)
        all_subsections.append({
            "id": section.section_id,
            "title": section.title,
            "anchor": section.section_id,
        })

    return {
        "slug": "home",
        "title": f"{repo_name} — Overview",
        "page_type": "home",
        "content": {
            "page_type": "home",
            "version": 2,
            "overview": {
                "name": repo_name,
                "project_description": system_narrative[:500],
                "system_type": fingerprint.system_type,
            },
            "system_narrative": system_narrative,
            "section_summaries": [
                {
                    "id": s.section_id,
                    "title": s.title,
                    "word_count": s.word_count,
                    "diagram_count": len(s.diagrams),
                }
                for s in enriched_sections
            ],
            "stats": {
                "modules": len(enriched_sections),
                "files": fingerprint.file_count,
                "loc": fingerprint.loc,
            },
            "module_list": [
                {
                    "name": s.title,
                    "slug": s.section_id,
                    "description": _first_text(s.prose_segments, 100),
                }
                for s in enriched_sections
            ],
            "prose_segments": all_segments,
            "system_context_diagram": system_context_diagram,
            "overview_diagram": overview_diagram,
            "diagrams": all_diagrams,
            "tables": all_tables,
            "source_links": all_source_links,
            "code_blocks": all_code_blocks,
            "subsections": all_subsections,
            "commit_hash": commit_hash,
        },
    }


def _render_multi_page(
    plan: WikiPlan,
    system_narrative: str,
    enriched_sections: list[EnrichedSection],
    repo_name: str,
    repo_url: str,
    fingerprint,
    commit_hash: str,
    overview_diagram: dict | None = None,
) -> list[dict[str, Any]]:
    """Render home + separate page per section."""
    pages: list[dict[str, Any]] = []

    # Home page
    pages.append(_render_home_page(
        plan, system_narrative, enriched_sections,
        repo_name, repo_url, fingerprint, commit_hash,
        overview_diagram=overview_diagram,
    ))

    # Section pages
    section_map = {s.section_id: s for s in enriched_sections}
    for section_plan in plan.sections:
        section = section_map.get(section_plan.id)
        if section:
            pages.append(_render_section_page(
                section, section_plan, commit_hash,
            ))

    return pages


def _render_home_page(
    plan: WikiPlan,
    system_narrative: str,
    enriched_sections: list[EnrichedSection],
    repo_name: str,
    repo_url: str,
    fingerprint,
    commit_hash: str,
    overview_diagram: dict | None = None,
) -> dict[str, Any]:
    """Render V2 home page — superset of V1 build_home_page() output."""
    from src.wiki.enricher import resolve_heading_markers
    total_words = sum(s.word_count for s in enriched_sections)
    system_context_diagram = _build_system_context_diagram(repo_name, repo_url, fingerprint)

    # Resolve headings in system narrative
    # We treat the system narrative as a single text segment initially
    initial_segments = [{"type": "text", "content": system_narrative}]
    prose_segments = resolve_heading_markers(initial_segments)

    content: dict[str, Any] = {
        "page_type": "home",
        "version": 2,
        "overview": {
            "name": repo_name,
            "project_description": system_narrative[:500],
            "system_type": fingerprint.system_type,
        },
        "system_narrative": system_narrative,
        "prose_segments": prose_segments,
        "section_summaries": [
            {
                "id": s.section_id,
                "title": s.title,
                "word_count": s.word_count,
                "diagram_count": len(s.diagrams),
            }
            for s in enriched_sections
        ],
        "stats": {
            "modules": len(enriched_sections),
            "files": fingerprint.file_count,
            "loc": fingerprint.loc,
            "total_words": total_words,
        },
        "module_list": [
            {
                "name": s.title,
                "slug": s.section_id,
                "description": _first_text(s.prose_segments, 100),
            }
            for s in enriched_sections
        ],
        "quick_links": [
            {"name": s.title, "slug": s.section_id}
            for s in enriched_sections
        ],
        "commit_hash": commit_hash,
        "suggested_reading_order": [s.section_id for s in enriched_sections],
        "system_context_diagram": system_context_diagram,
    }

    if overview_diagram:
        content["overview_diagram"] = overview_diagram
        content["diagrams"] = [d for d in [system_context_diagram, overview_diagram] if d]
    elif system_context_diagram:
        content["diagrams"] = [system_context_diagram]

    return {
        "slug": "home",
        "title": f"{repo_name} — Overview",
        "page_type": "home",
        "content": content,
    }


def _render_section_page(
    section: EnrichedSection,
    section_plan,
    commit_hash: str,
) -> dict[str, Any]:
    """Render a V2 section page — superset of V1 module page content."""
    # Build overview from first text segments
    purpose = _first_text(section.prose_segments, 200)

    # Extract how_it_works from first 500 chars of prose
    how_it_works = _first_text(section.prose_segments, 500)

    # Extract key_components, internal_deps, related_pages from enriched section
    # These are populated by the assembler agent
    raw = section.__dict__ if hasattr(section, '__dict__') else {}
    key_components = getattr(section, 'key_components', []) or []
    internal_deps = getattr(section, 'internal_deps', []) or []
    related_pages = getattr(section, 'related_pages', []) or []

    # Build dependencies from source_links (files referenced outside this section)
    section_files = set(
        section_plan.all_relevant_files if hasattr(section_plan, 'all_relevant_files') else []
    )
    dep_internal = sorted(set(internal_deps))
    dep_external = []
    # Detect external package imports from source links
    for link in section.source_links:
        fp = link.get("file_path", "")
        if fp and "/" not in fp and fp.endswith(".py"):
            dep_external.append(fp.replace(".py", ""))

    return {
        "slug": section.section_id,
        "title": section.title,
        "page_type": "module",
        "content": {
            "page_type": "module",
            "version": 2,
            "overview": {
                "purpose": purpose,
                "design_patterns": [],
                "data_flow": "",
            },
            "location": {
                "files": section_plan.all_relevant_files if hasattr(section_plan, 'all_relevant_files') else [],
                "file_count": len(section_plan.all_relevant_files) if hasattr(section_plan, 'all_relevant_files') else 0,
            },
            "prose_segments": section.prose_segments,
            "diagrams": section.diagrams,
            "tables": section.tables,
            "source_links": section.source_links,
            "code_blocks": section.code_blocks,
            "subsections": section.subsections,
            "how_it_works": how_it_works,
            "key_components": key_components,
            "dependencies": {"internal": dep_internal, "external": dep_external},
            "related_pages": related_pages,
            "known_issues": [],
            "security_notes": "",
            "configuration": "",
            "commit_hash": commit_hash,
        },
    }


def _first_text(segments: list[dict], max_len: int = 100) -> str:
    """Extract first N chars from text segments."""
    text_parts: list[str] = []
    for seg in segments:
        if seg.get("type") == "text":
            text_parts.append(seg.get("content", ""))
        if sum(len(t) for t in text_parts) >= max_len:
            break
    full = " ".join(text_parts).strip()
    return full[:max_len]


def _build_system_context_diagram(repo_name: str, repo_url: str, fingerprint) -> dict[str, str]:
    """Build a deterministic C4 Level 1 system-context diagram for the home page."""
    # Keep this stable and simple so every wiki has a reliable L1 context view.
    system_type = getattr(fingerprint, "system_type", "software system") or "software system"
    tools = [str(t).lower() for t in (getattr(fingerprint, "tools_present", []) or [])]

    externals = ["Git hosting"]
    if any(t in {"openai", "lm studio", "anthropic", "gemini", "llm"} for t in tools):
        externals.append("LLM provider")
    if any(t in {"postgresql", "mysql", "sqlite", "mongodb", "redis", "qdrant", "neo4j"} for t in tools):
        externals.append("Data stores")
    if any(t in {"docker", "kubernetes", "terraform", "ansible", "github actions"} for t in tools):
        externals.append("Infrastructure services")

    external_nodes = externals[:3]
    lines = [
        "graph LR",
        "  user([Developers / Operators])",
        f"  system[{repo_name}]",
        "  user -->|Uses| system",
    ]
    for idx, label in enumerate(external_nodes, start=1):
        node_id = f"ext{idx}"
        lines.append(f"  {node_id}[{label}]")
        lines.append(f"  system -->|Integrates with| {node_id}")

    return {
        "mermaid_source": "\n".join(lines),
        "caption": f"C4 Level 1 system context for {repo_name} ({system_type}) sourced from {repo_url}",
    }
