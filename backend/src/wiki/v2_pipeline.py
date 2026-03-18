"""V2 wiki generation pipeline — replaces Step 8 of analyze.py.

Orchestrates the multi-agent wiki pipeline:
  Phase 0: Compress — hierarchical code summarization (unchanged)
  Agent Pipeline: ARCHITECT → PLANNER → WRITER → [ANNOTATOR, DIAGRAMMER, TABULATOR] → ASSEMBLER
  Phase 4: Render — final page assembly

Also handles Module/WikiPage/CodeEntity persistence and
special page generation (Getting Started, Function Index, etc.).
"""

import logging
import time
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from src.dossier.schema import Dossier
from src.models.code_entity import CodeEntity as CodeEntityModel
from src.models.code_entity import EntityType, Module
from src.models.wiki import PageType, Wiki, WikiPage
from src.parsers.base import ParsedEntity
from src.recon.fingerprint import RepoFingerprint
from src.wiki.agents import run_wiki_pipeline
from src.wiki.agents.state import WikiState
from src.wiki.compressor import CodebaseCompressor
from src.wiki.interestingness import score_entities
from src.wiki.page_builders.module_page import slugify
from src.wiki.page_builders.special_pages import (
    build_api_reference,
    build_function_index,
    build_getting_started,
    build_glossary,
)
from src.wiki.renderer import render_wiki_pages
from src.wiki.v2_types import (
    EnrichedSection,
    WikiPlan,
    WikiSectionPlan,
    WikiSubsection,
)

logger = logging.getLogger(__name__)


def generate_wiki_v2(
    session: Session,
    wiki: Wiki,
    entities: list[ParsedEntity],
    modules_data: list[dict],
    repo_name: str,
    repo_url: str,
    repo_path: str,
    repository_id: str,
    fingerprint: RepoFingerprint,
    dossier: Dossier,
    commit_hash: str,
    page_progress_callback: Optional[Callable[[int, str], None]] = None,
) -> int:
    """Generate V2 wiki. Returns page count."""
    pages_created = 0

    def _report(name: str) -> None:
        nonlocal pages_created
        if page_progress_callback:
            page_progress_callback(pages_created, name)

    t_total = time.monotonic()

    # ── Prep: Build indexes from in-memory entities ──────────────────────
    t0 = time.monotonic()
    entity_index, name_to_qname = _build_entity_index(entities, repo_path)
    call_graph = _build_call_graph(entities, name_to_qname)
    reverse_call_graph = _build_reverse_call_graph(call_graph)
    
    # NEW: Build import graph for better diagrams
    import_graph = _build_import_graph(entities, repo_path)
    
    scored_entities = score_entities(entities)
    
    # Normalize all_files to repo-relative
    resolved_root = Path(repo_path).resolve()
    all_files_set = set()
    for e in entities:
        if e.entity_type == "module":
            continue
        rel = e.file_path
        try:
            rel = str(Path(e.file_path).resolve().relative_to(resolved_root))
        except ValueError:
            pass
        all_files_set.add(rel)
    all_files = sorted(list(all_files_set))

    logger.info(
        "V2 prep: %d entities indexed, %d call graph entries, %d imports (%.1fs)",
        len(entity_index), sum(len(v) for v in call_graph.values()),
        sum(len(v) for v in import_graph.values()),
        time.monotonic() - t0,
    )

    # ── Phase 0: Compress ────────────────────────────────────────────────
    t0 = time.monotonic()
    _report("Phase 0: Compressing codebase")
    compressor = CodebaseCompressor()
    compressed = compressor.compress(repo_path, entities, fingerprint, scored_entities)
    logger.info(
        "V2 Phase 0 (Compress): level=%s (%.1fs)",
        compressed.compression_level, time.monotonic() - t0,
    )

    # ── Agent Pipeline ───────────────────────────────────────────────────
    # Runs: ARCHITECT → PLANNER → WRITER → [ANNOTATOR, DIAGRAMMER, TABULATOR] → ASSEMBLER
    t0 = time.monotonic()
    _report("Initializing AI agents...")

    # Serialize compressed codebase for state
    compressed_dict = {
        "repo_summary": compressed.repo_summary,
        "file_summaries": {
            k: {
                "file_path": v.file_path, "language": v.language,
                "line_count": v.line_count, "summary": v.summary,
                "entity_count": v.entity_count, "key_entities": v.key_entities,
            }
            for k, v in compressed.file_summaries.items()
        },
        "directory_summaries": {
            k: {
                "dir_path": v.dir_path, "file_count": v.file_count,
                "summary": v.summary, "child_files": v.child_files,
                "key_entities": v.key_entities,
            }
            for k, v in compressed.directory_summaries.items()
        },
        "key_entities": compressed.key_entities,
        "call_graph_summary": compressed.call_graph_summary,
        "import_graph_summary": compressed.import_graph_summary,
        "compression_level": compressed.compression_level,
    }

    # Serialize fingerprint and dossier
    fp_dict = fingerprint.to_dict() if hasattr(fingerprint, "to_dict") else {}
    dossier_dict = dossier.to_dict() if hasattr(dossier, "to_dict") else {}

    initial_state: WikiState = {
        # Immutable inputs
        "entities": entities,
        "entity_index": entity_index,
        "call_graph": call_graph,
        "reverse_call_graph": reverse_call_graph,
        "import_graph": import_graph,
        "compressed": compressed_dict,
        "fingerprint": fp_dict,
        "dossier": dossier_dict,
        "repo_path": repo_path,
        "repo_url": repo_url,
        "commit_hash": commit_hash,
        "scored_entities": scored_entities,
        "all_files": all_files,
        "name_to_qname": name_to_qname,
        # Empty outputs (populated by agents)
        "architecture": {},
        "plan": {},
        "system_narrative": "",
        "narrated_sections": {},
        "annotated_sections": {},
        "section_diagrams": {},
        "section_tables": {},
        "overview_diagram": {},
        "enriched_sections": [],
        "agent_results": [],
    }

    final_state = run_wiki_pipeline(initial_state, progress_callback=_report, repo_id=repository_id)

    # Extract results from final state
    plan_dict = final_state.get("plan", {})
    system_narrative = final_state.get("system_narrative", "")
    enriched_section_dicts = final_state.get("enriched_sections", [])
    overview_diagram = final_state.get("overview_diagram") or None
    if overview_diagram and not overview_diagram.get("mermaid_source"):
        overview_diagram = None

    # Convert enriched section dicts to EnrichedSection objects
    enriched_sections = []
    for esd in enriched_section_dicts:
        enriched_sections.append(EnrichedSection(
            section_id=esd.get("section_id", ""),
            title=esd.get("title", ""),
            prose_segments=esd.get("prose_segments", []),
            diagrams=esd.get("diagrams", []),
            tables=esd.get("tables", []),
            source_links=esd.get("source_links", []),
            code_blocks=esd.get("code_blocks", []),
            subsections=esd.get("subsections", []),
            word_count=esd.get("word_count", 0),
            key_components=esd.get("key_components", []),
            internal_deps=esd.get("internal_deps", []),
            related_pages=esd.get("related_pages", []),
        ))

    # Reconstruct WikiPlan for persistence
    plan = _reconstruct_wiki_plan(plan_dict)

    total_words = sum(s.word_count for s in enriched_sections)
    total_diagrams = sum(len(s.diagrams) for s in enriched_sections)
    total_links = sum(len(s.source_links) for s in enriched_sections)
    logger.info(
        "Agent pipeline complete: %d words, %d diagrams, %d source links (%.1fs)",
        total_words, total_diagrams, total_links, time.monotonic() - t0,
    )

    # Log agent telemetry and move progress counter for agents
    agents_done = 0
    for result in final_state.get("agent_results", []):
        if isinstance(result, dict):
            agents_done += 1
            logger.info(
                "  Agent %s: success=%s elapsed=%.1fs",
                result.get("agent", "?"),
                result.get("success", "?"),
                result.get("elapsed", 0),
            )
            # Every 2 agents count as 1 'page' of progress to keep the number moving
            if agents_done % 2 == 0:
                pages_created += 1
                _report(f"Completed {result.get('agent')} analysis")

    # ── Phase 4: Render ──────────────────────────────────────────────────
    t0 = time.monotonic()
    _report("Phase 4: Rendering pages")
    rendered_pages = render_wiki_pages(
        plan, system_narrative, enriched_sections,
        repo_name, repo_url, fingerprint, commit_hash,
        overview_diagram=overview_diagram,
    )
    logger.info(
        "V2 Phase 4 (Render): %d pages (%.1fs)",
        len(rendered_pages), time.monotonic() - t0,
    )

    # ── Persist ──────────────────────────────────────────────────────────
    t0 = time.monotonic()
    _report("Persisting wiki pages")

    # 1. Delete ALL existing WikiPages for this wiki (clean slate)
    session.query(WikiPage).filter_by(wiki_id=wiki.id).delete()

    # 2. Delete existing Module records
    session.query(Module).filter_by(wiki_id=wiki.id).delete()
    session.flush()

    # 3. Create Module records matching V2 sections (for sidebar navigation)
    resolved_root = Path(repo_path).resolve()
    section_to_module: dict[str, Module] = {}

    for section_plan_item in plan.sections:
        enriched = next(
            (e for e in enriched_sections if e.section_id == section_plan_item.id),
            None,
        )
        desc = ""
        if enriched:
            desc = _first_text(enriched.prose_segments, 100)

        rel_files = section_plan_item.all_relevant_files

        mod = Module(
            wiki_id=wiki.id,
            name=section_plan_item.title,
            slug=section_plan_item.id,
            description=desc,
            file_paths=rel_files,
            file_count=len(rel_files),
        )
        session.add(mod)
        session.flush()
        section_to_module[section_plan_item.id] = mod

    # 4. Create CodeEntity records associated with new Module records
    _persist_code_entities(session, entities, section_to_module, plan, resolved_root)

    # 5. Create WikiPage records from rendered_pages and link modules
    for page_data in rendered_pages:
        page = WikiPage(
            wiki_id=wiki.id,
            page_type=PageType(page_data["page_type"]),
            title=page_data["title"],
            slug=page_data["slug"],
            content=page_data["content"],
            source_files=page_data["content"].get("location", {}).get("files", []),
            commit_hash=commit_hash,
        )
        session.add(page)
        session.flush()

        # Link module to its wiki page
        if page_data["page_type"] == "module":
            mod = section_to_module.get(page_data["slug"])
            if mod:
                mod.wiki_page_id = page.id

        pages_created += 1
        _report(f"Generated {page_data['title']}")

    session.flush()

    # 6. Generate + persist special pages (unchanged builders)
    # Collect prose text from enriched sections for glossary enrichment
    module_prose_texts = [
        seg.get("content", "") for s in enriched_sections
        for seg in s.prose_segments
        if isinstance(seg, dict) and seg.get("type") == "text"
    ]
    pages_created += _generate_special_pages(
        session, wiki, entities, repo_name, repo_path,
        fingerprint, commit_hash, _report,
        system_narrative=system_narrative,
        module_prose=module_prose_texts,
    )

    session.commit()

    total_elapsed = time.monotonic() - t_total
    logger.info(
        "V2 pipeline complete: %d pages, %d words, %d diagrams, "
        "%d source links (%.1fs total)",
        pages_created, total_words, total_diagrams, total_links, total_elapsed,
    )

    return pages_created


# ── Internal helpers ─────────────────────────────────────────────────────────


def _reconstruct_wiki_plan(plan_dict: dict) -> WikiPlan:
    """Reconstruct a WikiPlan object from the agent state dict."""
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


def _build_entity_index(
    entities: list[ParsedEntity],
    repo_path: str,
) -> tuple[dict[str, dict], dict[str, str]]:
    """Build entity index and name→qname lookup from parsed entities.

    Converts absolute cache paths to repo-relative.
    """
    resolved_root = Path(repo_path).resolve()
    entity_index: dict[str, dict] = {}
    name_to_qname: dict[str, str] = {}

    for e in entities:
        # Normalize to repo-relative path
        rel_path = e.file_path
        try:
            rel_path = str(Path(e.file_path).resolve().relative_to(resolved_root))
        except ValueError:
            pass

        entity_index[e.qualified_name] = {
            "file_path": rel_path,
            "line_start": e.line_start,
            "name": e.name,
            "entity_type": e.entity_type,
            "signature": e.signature or "",
        }

        # First-seen wins for short name lookup
        if e.name not in name_to_qname:
            name_to_qname[e.name] = e.qualified_name

    return entity_index, name_to_qname


def _build_call_graph(
    entities: list[ParsedEntity],
    name_to_qname: dict[str, str],
) -> dict[str, list[str]]:
    """Build caller→[callees] graph with fuzzy name resolution."""
    qnames = {e.qualified_name for e in entities}
    graph: dict[str, list[str]] = {}

    for e in entities:
        if not e.calls:
            continue
        callees: list[str] = []
        for callee in e.calls:
            if callee in qnames:
                callees.append(callee)
            elif callee in name_to_qname:
                callees.append(name_to_qname[callee])
        if callees:
            graph[e.qualified_name] = callees

    return graph


def _build_reverse_call_graph(
    call_graph: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Invert caller→[callees] to callee→[callers]."""
    reverse: dict[str, list[str]] = {}
    for caller, callees in call_graph.items():
        for callee in callees:
            reverse.setdefault(callee, []).append(caller)
    return reverse


def _build_import_graph(
    entities: list[ParsedEntity],
    repo_path: str,
) -> dict[str, list[str]]:
    """Build file-to-file import graph.
    
    Returns:
        Dict of {importer_rel_path: [imported_rel_paths]}
    """
    import os
    resolved_root = Path(repo_path).resolve()
    
    # Map from module name (qualified_name) to relative file path
    # e.g. "ui.lib.api" -> "ui/lib/api.ts"
    module_to_path: dict[str, str] = {}
    for e in entities:
        if e.entity_type == "module":
            rel = e.file_path
            try:
                rel = str(Path(e.file_path).resolve().relative_to(resolved_root))
            except ValueError:
                pass
            module_to_path[e.qualified_name] = rel
            
    graph: dict[str, list[str]] = {}
    for e in entities:
        if e.entity_type == "module" and e.imports:
            rel_src = e.file_path
            try:
                rel_src = str(Path(e.file_path).resolve().relative_to(resolved_root))
            except ValueError:
                pass
                
            targets: list[str] = []
            for imp in e.imports:
                if imp in module_to_path:
                    targets.append(module_to_path[imp])
                else:
                    # Try matching by suffix
                    # e.g. imp="python-backend.server" -> file="python-backend/server.py"
                    suffix = imp.replace(".", "/")
                    for mod_name, rel_path in module_to_path.items():
                        if rel_path.startswith(suffix) or suffix.endswith(os.path.splitext(rel_path)[0]):
                            targets.append(rel_path)
                            break
            if targets:
                graph[rel_src] = list(set(targets))
                
    return graph


def _persist_code_entities(
    session: Session,
    entities: list[ParsedEntity],
    section_to_module: dict[str, Module],
    plan,
    resolved_root: Path,
) -> None:
    """Associate CodeEntity records with the V2 Module records."""
    # Build file→section mapping
    file_to_section: dict[str, str] = {}
    for section in plan.sections:
        for f in section.all_relevant_files:
            if f not in file_to_section:
                file_to_section[f] = section.id

    seen_qnames: set[str] = set()

    for entity in entities:
        if entity.entity_type == "module":
            continue
        if entity.qualified_name in seen_qnames:
            continue
        seen_qnames.add(entity.qualified_name)

        # Normalize path
        rel_path = entity.file_path
        try:
            rel_path = str(Path(entity.file_path).resolve().relative_to(resolved_root))
        except ValueError:
            pass

        # Find which module this entity belongs to
        section_id = file_to_section.get(rel_path)
        if not section_id:
            # Try matching by directory
            for section in plan.sections:
                if any(rel_path.startswith(str(Path(f).parent)) for f in section.all_relevant_files):
                    section_id = section.id
                    break

        if not section_id:
            # Assign to first section as fallback
            if plan.sections:
                section_id = plan.sections[0].id

        module = section_to_module.get(section_id)
        if not module:
            continue

        db_entity = CodeEntityModel(
            module_id=module.id,
            name=entity.name,
            qualified_name=entity.qualified_name,
            entity_type=next(
                (e for e in EntityType if e.value == entity.entity_type),
                EntityType.function,
            ),
            file_path=rel_path,
            line_start=entity.line_start,
            line_end=entity.line_end,
            signature=entity.signature,
            docstring=entity.docstring,
            entity_metadata=entity.entity_metadata,
        )
        session.add(db_entity)

    session.flush()


def _generate_special_pages(
    session: Session,
    wiki: Wiki,
    entities: list[ParsedEntity],
    repo_name: str,
    repo_path: str,
    fingerprint: RepoFingerprint,
    commit_hash: str,
    report_callback,
    system_narrative: str = "",
    module_prose: list[str] | None = None,
) -> int:
    """Generate special pages using existing V1 builders. Returns count."""
    pages = 0

    try:
        gs_content = build_getting_started(repo_name, repo_path, fingerprint.to_dict())
        session.add(WikiPage(
            wiki_id=wiki.id, page_type=PageType.getting_started,
            title="Getting Started", slug="getting-started",
            content=gs_content, commit_hash=commit_hash,
        ))
        pages += 1
        report_callback("Getting Started")
    except Exception as exc:
        logger.warning("Getting started page failed: %s", exc)

    try:
        fi_content = build_function_index(entities, repo_path)
        session.add(WikiPage(
            wiki_id=wiki.id, page_type=PageType.function_index,
            title="Function Index", slug="function-index",
            content=fi_content, commit_hash=commit_hash,
        ))
        pages += 1
        report_callback("Function Index")
    except Exception as exc:
        logger.warning("Function index page failed: %s", exc)

    try:
        glossary_content = build_glossary(entities, repo_path, system_narrative=system_narrative, module_prose=module_prose)
        session.add(WikiPage(
            wiki_id=wiki.id, page_type=PageType.glossary,
            title="Glossary", slug="glossary",
            content=glossary_content, commit_hash=commit_hash,
        ))
        pages += 1
        report_callback("Glossary")
    except Exception as exc:
        logger.warning("Glossary page failed: %s", exc)

    try:
        api_content = build_api_reference(entities, repo_path)
        session.add(WikiPage(
            wiki_id=wiki.id, page_type=PageType.api_reference,
            title="API Reference", slug="api-reference",
            content=api_content, commit_hash=commit_hash,
        ))
        pages += 1
        report_callback("API Reference")
    except Exception as exc:
        logger.warning("API reference page failed: %s", exc)

    session.flush()
    return pages


def _build_overview_diagram(
    plan,
    enriched_sections: list,
    entity_index: dict[str, dict],
    call_graph: dict[str, list[str]],
) -> dict | None:
    """Build a repo-level overview diagram showing cross-section dependencies.

    Draws section→section edges when entities in one section call entities in another.
    """
    import re

    # Map entity qname → section_id
    entity_to_section: dict[str, str] = {}
    for section_plan in plan.sections:
        file_set = set(section_plan.all_relevant_files)
        for qname, info in entity_index.items():
            if info.get("file_path") in file_set:
                entity_to_section[qname] = section_plan.id

    # Find cross-section edges
    section_edges: dict[tuple[str, str], int] = {}
    for caller, callees in call_graph.items():
        caller_section = entity_to_section.get(caller)
        if not caller_section:
            continue
        for callee in callees:
            callee_section = entity_to_section.get(callee)
            if callee_section and callee_section != caller_section:
                key = (caller_section, callee_section)
                section_edges[key] = section_edges.get(key, 0) + 1

    if len(section_edges) < 2:
        return None

    # Build section title map
    section_titles = {s.id: s.title for s in plan.sections}

    def safe_id(s: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_]", "_", s)

    lines = ["graph LR"]
    # Add nodes for all sections that appear in edges
    nodes = set()
    for src, dst in section_edges:
        nodes.add(src)
        nodes.add(dst)
    for node in sorted(nodes):
        sid = safe_id(node)
        title = section_titles.get(node, node)
        lines.append(f"    {sid}[{title}]")

    for (src, dst), count in section_edges.items():
        label = f"|{count}|" if count > 1 else ""
        lines.append(f"    {safe_id(src)} -->{label} {safe_id(dst)}")

    mermaid_source = "\n".join(lines)
    caption = (
        f"Repository Overview — {len(nodes)} sections, "
        f"{len(section_edges)} cross-section dependencies"
    )
    return {"mermaid_source": mermaid_source, "caption": caption}


def _first_text(segments: list[dict], max_len: int = 100) -> str:
    """Extract first N chars from text segments."""
    parts: list[str] = []
    for seg in segments:
        if seg.get("type") == "text":
            parts.append(seg.get("content", ""))
        if sum(len(t) for t in parts) >= max_len:
            break
    return " ".join(parts).strip()[:max_len]
