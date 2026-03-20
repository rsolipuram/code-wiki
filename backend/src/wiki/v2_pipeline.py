"""V2 wiki generation pipeline — replaces Step 8 of analyze.py.

Orchestrates the multi-agent wiki pipeline:
  Phase 0: Compress — hierarchical code summarization (unchanged)
  Agent Pipeline: ARCHITECT → PLANNER → WRITER → [ANNOTATOR, DIAGRAMMER, TABULATOR] → ASSEMBLER
  Phase 4: Render — final page assembly

Also handles Module/WikiPage/CodeEntity persistence and
special page generation (Getting Started, Function Index, etc.).
"""

import logging
import re
import statistics
import time
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from src.config import get_settings
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
) -> dict[str, Any]:
    """Generate V2 wiki. Returns page count + generation warnings."""
    pages_created = 0
    generation_warnings: list[dict[str, str]] = []
    quality_metrics: dict[str, Any] = {}

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
    
    # ── Phase 2A: Extract domain entities (agents, tools, guardrails) ────
    domain_entities = _extract_domain_entities(entity_index, call_graph, repo_path)
    logger.info(
        "Domain entities: %d agents, %d tools, %d guardrails",
        len(domain_entities.get("agents", [])),
        len(domain_entities.get("tools", [])),
        len(domain_entities.get("guardrails", [])),
    )
    
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
        # Domain entity summary (derived, used by all agents)
        "domain_entities": domain_entities,
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
    _inject_runtime_holistic_sections(
        rendered_pages=rendered_pages,
        plan=plan,
        entity_index=entity_index,
        call_graph=call_graph,
        domain_entities=domain_entities,
    )
    _sanitize_rendered_pages(rendered_pages)
    quality_warnings, quality_metrics = _evaluate_rendered_page_quality(
        rendered_pages=rendered_pages,
        all_files=all_files,
        repo_path=repo_path,
        entity_index=entity_index,
        domain_entities=domain_entities,
    )
    generation_warnings.extend(quality_warnings)
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

    # 3b. Wire dependency_module_ids from architect component graph
    _wire_module_dependencies(
        section_to_module,
        final_state.get("architecture", {}),
        plan=plan,
        entity_index=entity_index,
        call_graph=call_graph,
    )

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
    special_pages_created, special_page_warnings = _generate_special_pages(
        session, wiki, entities, repo_name, repo_path,
        repo_url, fingerprint, commit_hash, _report,
        system_narrative=system_narrative,
        module_prose=module_prose_texts,
        domain_entities=domain_entities,
    )
    pages_created += special_pages_created
    generation_warnings.extend(special_page_warnings)

    # Explicit degradation signal for sections expected to have diagrams but ending with none.
    for section_plan in plan.sections:
        if getattr(section_plan, "diagram_type", "none") == "none":
            continue
        enriched = next((s for s in enriched_sections if s.section_id == section_plan.id), None)
        if not enriched:
            continue
        if not enriched.diagrams:
            generation_warnings.append({
                "page": section_plan.id,
                "reason": "diagram_generation_empty",
                "detail": "No valid diagrams generated; content rendered without diagrams.",
            })

    if generation_warnings:
        home_db = (
            session.query(WikiPage)
            .filter(WikiPage.wiki_id == wiki.id, WikiPage.slug == "home")
            .first()
        )
        if home_db and isinstance(home_db.content, dict):
            updated_home_content = dict(home_db.content)
            updated_home_content["generation_status"] = "degraded"
            updated_home_content["generation_warnings"] = generation_warnings
            home_db.content = updated_home_content

    session.commit()

    total_elapsed = time.monotonic() - t_total
    logger.info(
        "V2 pipeline complete: %d pages, %d words, %d diagrams, "
        "%d source links, %d warnings (%.1fs total)",
        pages_created, total_words, total_diagrams, total_links, len(generation_warnings), total_elapsed,
    )

    return {
        "pages_created": pages_created,
        "generation_warnings": generation_warnings,
        "quality_metrics": quality_metrics,
    }


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


def _wire_module_dependencies(
    section_to_module: dict[str, "Module"],
    architecture: dict,
    plan: "WikiPlan | None" = None,
    entity_index: dict[str, dict] | None = None,
    call_graph: dict[str, list[str]] | None = None,
) -> None:
    """Populate dependency_module_ids on each Module using architect component graph.

    The architect produces components[].dependencies as a list of component *names*.
    We resolve those names to module IDs via two strategies:
      1. Slugify the dependency name and look it up in section_to_module (exact match).
      2. Case-insensitive title match against module names (fallback).
    """
    if not section_to_module:
        return

    # Build reverse lookups
    slug_to_module = section_to_module  # already keyed by slug
    title_to_module = {mod.name.lower().strip(): mod for mod in section_to_module.values()}
    if architecture:
        components = architecture.get("components", []) or []
        for comp in components:
            comp_name = comp.get("name", "")
            comp_slug = slugify(comp_name)
            mod = slug_to_module.get(comp_slug) or title_to_module.get(comp_name.lower().strip())
            if not mod:
                continue

            dep_names = comp.get("dependencies", []) or []
            dep_ids: list[str] = []
            for dep_name in dep_names:
                dep_slug = slugify(dep_name)
                dep_mod = (
                    slug_to_module.get(dep_slug)
                    or title_to_module.get(dep_name.lower().strip())
                )
                if dep_mod and dep_mod.id != mod.id:
                    dep_ids.append(dep_mod.id)

            if dep_ids:
                mod.dependency_module_ids = dep_ids
                logger.debug(
                    "DEPS: %s → %d dependencies wired",
                    comp_name,
                    len(dep_ids),
                )

    # Fallback heuristic: infer related modules from cross-section call graph.
    has_any_dependencies = any((m.dependency_module_ids or []) for m in section_to_module.values())
    if has_any_dependencies or not (plan and entity_index and call_graph):
        return

    section_files = {
        section.id: set(getattr(section, "all_relevant_files", []) or [])
        for section in plan.sections
    }
    qname_to_section: dict[str, str] = {}
    for qname, info in entity_index.items():
        file_path = info.get("file_path")
        if not file_path:
            continue
        for section_id, files in section_files.items():
            if file_path in files:
                qname_to_section[qname] = section_id
                break

    edge_weights: dict[tuple[str, str], int] = {}
    for caller, callees in call_graph.items():
        src = qname_to_section.get(caller)
        if not src:
            continue
        for callee in callees:
            dst = qname_to_section.get(callee)
            if dst and dst != src:
                edge_weights[(src, dst)] = edge_weights.get((src, dst), 0) + 1

    for section_id, mod in section_to_module.items():
        if mod.dependency_module_ids:
            continue

        ranked = sorted(
            (
                (dst, weight)
                for (src, dst), weight in edge_weights.items()
                if src == section_id and dst in section_to_module
            ),
            key=lambda item: item[1],
            reverse=True,
        )

        dep_ids = [section_to_module[dst].id for dst, _ in ranked[:3]]

        # If graph inference yields nothing, fall back to adjacent reading-path modules.
        if not dep_ids and plan.sections:
            ordered_ids = [s.id for s in plan.sections if s.id in section_to_module]
            try:
                idx = ordered_ids.index(section_id)
                neighbors = [ordered_ids[i] for i in (idx - 1, idx + 1) if 0 <= i < len(ordered_ids)]
                dep_ids = [section_to_module[n].id for n in neighbors if n != section_id]
            except ValueError:
                dep_ids = []

        if dep_ids:
            mod.dependency_module_ids = dep_ids
            logger.debug("DEPS fallback: %s → %d inferred dependencies", section_id, len(dep_ids))


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
            "docstring": (e.docstring or "")[:200],
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
    repo_url: str,
    fingerprint: RepoFingerprint,
    commit_hash: str,
    report_callback,
    system_narrative: str = "",
    module_prose: list[str] | None = None,
    domain_entities: dict | None = None,
) -> tuple[int, list[dict[str, str]]]:
    """Generate special pages using V1 builders. Returns (count, warnings)."""
    pages = 0
    warnings: list[dict[str, str]] = []

    try:
        gs_content = build_getting_started(
            repo_name,
            repo_path,
            fingerprint.to_dict(),
            repo_url=repo_url,
            analysis_id=wiki.repository_id,
        )
        gs_content["commit_hash"] = commit_hash
        gs_meta = gs_content.get("_meta", {}) if isinstance(gs_content, dict) else {}
        if gs_meta.get("fallback_used"):
            warnings.append({
                "page": "getting-started",
                "reason": gs_meta.get("error_type", "generation_fallback"),
                "detail": str(gs_meta.get("error", ""))[:250],
            })
        session.add(WikiPage(
            wiki_id=wiki.id, page_type=PageType.getting_started,
            title="Getting Started", slug="getting-started",
            content=gs_content, commit_hash=commit_hash,
        ))
        pages += 1
        report_callback("Getting Started")
    except Exception as exc:
        logger.warning("Getting started page failed: %s", exc)
        warnings.append({
            "page": "getting-started",
            "reason": type(exc).__name__,
            "detail": str(exc)[:250],
        })

    try:
        fi_content = build_function_index(entities, repo_path, domain_entities=domain_entities)
        fi_content["commit_hash"] = commit_hash
        session.add(WikiPage(
            wiki_id=wiki.id, page_type=PageType.function_index,
            title="Function Index", slug="function-index",
            content=fi_content, commit_hash=commit_hash,
        ))
        pages += 1
        report_callback("Function Index")
    except Exception as exc:
        logger.warning("Function index page failed: %s", exc)
        warnings.append({
            "page": "function-index",
            "reason": type(exc).__name__,
            "detail": str(exc)[:250],
        })

    try:
        glossary_content = build_glossary(
            entities,
            repo_path,
            system_narrative=system_narrative,
            module_prose=module_prose,
            analysis_id=wiki.repository_id,
            domain_entities=domain_entities,
        )
        glossary_content["commit_hash"] = commit_hash
        glossary_meta = glossary_content.get("_meta", {}) if isinstance(glossary_content, dict) else {}
        if glossary_meta.get("fallback_used"):
            warnings.append({
                "page": "glossary",
                "reason": glossary_meta.get("error_type", "generation_fallback"),
                "detail": str(glossary_meta.get("error", ""))[:250],
            })
        session.add(WikiPage(
            wiki_id=wiki.id, page_type=PageType.glossary,
            title="Glossary", slug="glossary",
            content=glossary_content, commit_hash=commit_hash,
        ))
        pages += 1
        report_callback("Glossary")
    except Exception as exc:
        logger.warning("Glossary page failed: %s", exc)
        warnings.append({
            "page": "glossary",
            "reason": type(exc).__name__,
            "detail": str(exc)[:250],
        })

    try:
        api_content = build_api_reference(entities, repo_path)
        api_content["commit_hash"] = commit_hash
        session.add(WikiPage(
            wiki_id=wiki.id, page_type=PageType.api_reference,
            title="API Reference", slug="api-reference",
            content=api_content, commit_hash=commit_hash,
        ))
        pages += 1
        report_callback("API Reference")
    except Exception as exc:
        logger.warning("API reference page failed: %s", exc)
        warnings.append({
            "page": "api-reference",
            "reason": type(exc).__name__,
            "detail": str(exc)[:250],
        })

    session.flush()
    return pages, warnings


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


def _extract_domain_entities(
    entity_index: dict[str, dict],
    call_graph: dict[str, list[str]],
    repo_path: str,
) -> dict:
    """Extract domain-level actors from entity index.

    Identifies agents, tools, and guardrails by name pattern and file location.
    Returns a DomainEntitySummary with: agents, tools, guardrails, all_names.
    """
    _AGENT_SUFFIXES = (
        "agent", "handler", "controller", "service", "processor",
        "bot", "actor", "runner", "worker", "flow", "pipeline",
    )
    # Also detect classes in files named agent*.py / *_agent.py / agents/*.py
    _AGENT_FILE_PATTERNS = ("/agent", "agents/", "_agent.", "-agent.")
    _TOOL_FILE_PATTERNS = ("/tools.py", "/tools.ts", "/tool.py", "/tools/", "tools.js")
    _GUARDRAIL_PATTERNS = ("guardrail", "guard", "validator", "middleware", "filter")

    agents: list[dict] = []
    tools: list[dict] = []
    guardrails: list[dict] = []
    seen: set[str] = set()

    # Build reverse mapping: qname → entity info with tool list from call graph
    for qname, info in entity_index.items():
        name = str(info.get("name", ""))
        entity_type = str(info.get("entity_type", ""))
        file_path = str(info.get("file_path", ""))
        if not name or name.startswith("_") or name in seen:
            continue
        if entity_type not in ("class", "function"):
            continue

        name_lower = name.lower()
        file_lower = file_path.lower()
        docstring = str(info.get("docstring", "") or "")

        # ── Agents: classes by suffix OR by agent file location ──
        is_agent_by_suffix = (
            entity_type == "class"
            and any(name_lower.endswith(s) for s in _AGENT_SUFFIXES)
            and not file_lower.endswith((".tsx", ".ts"))
            and not name_lower.endswith("props")
            and name_lower not in ("agent", "baseagent", "abstractagent")
        )
        is_agent_by_file = (
            entity_type == "class"
            and any(p in file_lower for p in _AGENT_FILE_PATTERNS)
            and not file_lower.endswith((".tsx", ".ts"))
            and not name_lower.endswith("props")
            and name_lower not in ("agent", "baseagent", "abstractagent")
        )
        if is_agent_by_suffix or is_agent_by_file:
            # Find handoff targets (other agent-like callees)
            callees = call_graph.get(qname, [])
            handoff_targets = []
            tool_names = []
            for callee in callees:
                callee_info = entity_index.get(callee, {})
                callee_name = str(callee_info.get("name", ""))
                callee_type = str(callee_info.get("entity_type", ""))
                if any(callee_name.lower().endswith(s) for s in _AGENT_SUFFIXES):
                    handoff_targets.append(callee_name)
                elif callee_type == "function" and any(
                    p in str(callee_info.get("file_path", "")).lower()
                    for p in _TOOL_FILE_PATTERNS
                ):
                    tool_names.append(callee_name)
            agents.append({
                "name": name,
                "qualified_name": qname,
                "file": file_path,
                "docstring": docstring[:200],
                "handoff_targets": handoff_targets[:6],
                "tools": tool_names[:8],
            })
            seen.add(name)
            continue

        # ── Tools: functions in tools files ──
        if entity_type == "function" and any(p in file_lower for p in _TOOL_FILE_PATTERNS):
            tools.append({
                "name": name,
                "qualified_name": qname,
                "file": file_path,
                "docstring": docstring[:150],
            })
            seen.add(name)
            continue

        # ── Guardrails: any entity with guardrail-related naming ──
        if any(p in name_lower for p in _GUARDRAIL_PATTERNS):
            guardrails.append({
                "name": name,
                "qualified_name": qname,
                "file": file_path,
                "docstring": docstring[:150],
            })
            seen.add(name)

    # ── SDK Instantiation Pattern: var = Agent[...](name="...", ...) ───────────
    # Catches repos using OpenAI Agents SDK, LangChain, AutoGen, CrewAI etc.
    # where agents are instances not subclasses.
    _SDK_AGENT_RE = re.compile(
        r'^(?P<var>[a-z_][a-z0-9_]*)\s*=\s*\bAgent(?:\[[^\]]*\])?\s*\(',
        re.MULTILINE,
    )
    _AGENT_NAME_RE = re.compile(r'\bname\s*=\s*["\'](?P<name>[^"\']+)["\']')
    _AGENT_FILE_RE = re.compile(r'(?:^|/)agents?(?:\.py|/\w+\.py)$', re.IGNORECASE)

    seen_sdk: set[str] = set()
    if repo_path:
        agent_files = [
            info.get("file_path", "")
            for info in entity_index.values()
            if _AGENT_FILE_RE.search(str(info.get("file_path", "")))
        ]
        for rel_path in set(agent_files):
            abs_path = Path(repo_path) / rel_path
            try:
                source = abs_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in _SDK_AGENT_RE.finditer(source):
                var_name = m.group("var")
                if var_name in seen_sdk or var_name in seen:
                    continue
                # Extract `name="..."` from the same Agent(...) call block
                call_start = m.end()
                # Grab up to 500 chars after the `Agent(` to find the name= arg
                snippet = source[call_start : call_start + 500]
                name_m = _AGENT_NAME_RE.search(snippet)
                display_name = name_m.group("name") if name_m else var_name.replace("_", " ").title()
                # Extract tools list from snippet
                tool_match = re.search(r'tools\s*=\s*\[([^\]]*)\]', snippet)
                tool_list = []
                if tool_match:
                    tool_list = [t.strip() for t in tool_match.group(1).split(",") if t.strip()][:8]
                # Extract handoff_description
                hdesc_m = re.search(r'handoff_description\s*=\s*["\']([^"\']+)["\']', snippet)
                hdesc = hdesc_m.group(1)[:200] if hdesc_m else ""
                agents.append({
                    "name": display_name,
                    "qualified_name": f"{rel_path}::{var_name}",
                    "file": rel_path,
                    "docstring": hdesc,
                    "handoff_targets": [],
                    "tools": tool_list,
                    "var_name": var_name,
                })
                seen_sdk.add(var_name)
                seen.add(display_name)

    all_names = [e["name"] for e in agents] + [e["name"] for e in tools] + [e["name"] for e in guardrails]
    return {
        "agents": agents,
        "tools": tools,
        "guardrails": guardrails,
        "all_names": all_names,
        "agent_count": len(agents),
    }


_PLACEHOLDER_PATTERNS = (
    re.compile(r"\[code:\s*[^\]]+\]", re.IGNORECASE),
    re.compile(r"representative line range", re.IGNORECASE),
    re.compile(r"would be here", re.IGNORECASE),
    re.compile(r"\bplaceholder\b", re.IGNORECASE),
)
_PATH_PATTERN = re.compile(r"\b[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+){1,}\.(?:py|ts|tsx|js|jsx|json|md|yaml|yml)\b")
_ENDPOINT_PATTERN = re.compile(r"(?<![a-zA-Z0-9_])/[-a-zA-Z0-9_/{}/:]+")
_URL_PATTERN = re.compile(r"https?://[^\s)\]>]+", re.IGNORECASE)
_LEAKED_CODE_MARKER_RE = re.compile(r"\[code:\s*.*?\]", re.IGNORECASE | re.DOTALL)
_ENDPOINT_CONTEXT_HINT_RE = re.compile(
    r"\b(endpoint|route|routes|api|http|get|post|put|delete|patch)\b",
    re.IGNORECASE,
)
_ROUTER_DEF_RE = re.compile(r"(?P<name>\w+)\s*=\s*APIRouter\((?P<args>.*?)\)", re.DOTALL)
_ROUTE_DECORATOR_RE = re.compile(
    r"@(?P<router>\w+)\.(?:get|post|put|delete|patch|options|head)\(\s*"
    r"(?P<quote>[\"'])(?P<path>[^\"']+)(?P=quote)"
)
_INCLUDE_ROUTER_RE = re.compile(r"include_router\((?P<args>.*?)\)", re.DOTALL)
_PREFIX_RE = re.compile(r"prefix\s*=\s*(?P<quote>[\"'])(?P<prefix>[^\"']*)(?P=quote)")
_SKIP_ROUTE_SCAN_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"}


def _normalize_text(text: str) -> str:
    lowered = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", lowered).strip()


def _tokenize_text(text: str) -> set[str]:
    normalized = _normalize_text(text)
    return set(normalized.split()) if normalized else set()


def _jaccard_similarity_from_tokens(a_tokens: set[str], b_tokens: set[str]) -> float:
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)


def _normalize_endpoint_path(path: str) -> str:
    """Normalize endpoint path for robust comparisons."""
    normalized = path.strip()
    if not normalized:
        return ""
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    normalized = re.sub(r"/{2,}", "/", normalized)
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized[:-1]
    return normalized


def _is_likely_endpoint_reference(text: str, start: int, end: int, endpoint: str) -> bool:
    """Filter path-like tokens that are not API endpoint references."""
    # Strong endpoint signals
    if endpoint.startswith("/v") or "{" in endpoint or ":" in endpoint:
        return True
    if endpoint.startswith("/api/") or endpoint.startswith("/v1/") or endpoint.startswith("/v2/"):
        return True

    # Contextual hint nearby in prose
    window = text[max(0, start - 48):min(len(text), end + 24)]
    if _ENDPOINT_CONTEXT_HINT_RE.search(window):
        return True

    # Plain filesystem-like paths (e.g., /src, /src/agent, /core/orchestrator) are not endpoints.
    return False


def _collect_route_paths(repo_path: str) -> set[str]:
    """Collect FastAPI-like route paths from the analyzed repository."""
    root = Path(repo_path).resolve()
    if not root.exists():
        return set()

    route_paths: set[str] = set()
    include_prefixes: set[str] = set()

    for file in root.rglob("*.py"):
        if any(part in _SKIP_ROUTE_SCAN_DIRS for part in file.parts):
            continue
        try:
            content = file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        router_prefixes: dict[str, str] = {}
        for m in _ROUTER_DEF_RE.finditer(content):
            prefix_match = _PREFIX_RE.search(m.group("args"))
            router_prefixes[m.group("name")] = (
                _normalize_endpoint_path(prefix_match.group("prefix")) if prefix_match else ""
            )

        for m in _ROUTE_DECORATOR_RE.finditer(content):
            route = _normalize_endpoint_path(m.group("path"))
            if not route:
                continue
            route_paths.add(route)
            local_prefix = router_prefixes.get(m.group("router"), "")
            route_paths.add(_normalize_endpoint_path(f"{local_prefix}{route}"))

        for m in _INCLUDE_ROUTER_RE.finditer(content):
            prefix_match = _PREFIX_RE.search(m.group("args"))
            if prefix_match:
                include_prefix = _normalize_endpoint_path(prefix_match.group("prefix"))
                if include_prefix:
                    include_prefixes.add(include_prefix)

    if not route_paths:
        return set()

    expanded = set(route_paths)
    for prefix in include_prefixes:
        for route in route_paths:
            expanded.add(_normalize_endpoint_path(f"{prefix}{route}"))
    return {path for path in expanded if path}


def _extract_page_text(content: dict[str, Any], *, include_diagram_captions: bool = True) -> str:
    chunks: list[str] = []
    if isinstance(content.get("system_narrative"), str):
        chunks.append(content["system_narrative"])
    for seg in content.get("prose_segments", []) or []:
        if not isinstance(seg, dict):
            continue
        seg_type = str(seg.get("type", "")).lower()
        if seg_type == "text":
            chunks.append(str(seg.get("content", "")))
        elif seg_type == "heading":
            chunks.append(str(seg.get("text", "")))
    for table in content.get("tables", []) or []:
        if isinstance(table, dict):
            if isinstance(table.get("caption"), str):
                chunks.append(table["caption"])
            for row in table.get("rows", []) or []:
                if isinstance(row, list):
                    chunks.append(" ".join(str(c) for c in row))
    if include_diagram_captions:
        for diagram in content.get("diagrams", []) or []:
            if isinstance(diagram, dict) and isinstance(diagram.get("caption"), str):
                chunks.append(diagram["caption"])
    return "\n".join(chunks)


def _sanitize_rendered_pages(rendered_pages: list[dict[str, Any]]) -> None:
    """Drop duplicate section-like items to reduce noisy repetition."""
    for page in rendered_pages:
        content = page.get("content")
        if not isinstance(content, dict):
            continue

        related = content.get("related_pages")
        if isinstance(related, list):
            seen: set[str] = set()
            deduped = []
            for item in related:
                if not isinstance(item, dict):
                    continue
                slug = str(item.get("slug", "")).strip()
                if not slug or slug in seen:
                    continue
                seen.add(slug)
                deduped.append(item)
            content["related_pages"] = deduped

        tables = content.get("tables")
        if isinstance(tables, list):
            seen_sigs: set[str] = set()
            deduped_tables = []
            for table in tables:
                if not isinstance(table, dict):
                    continue
                headers = table.get("headers", [])
                rows = table.get("rows", [])
                caption = table.get("caption", "")
                sig = _normalize_text(
                    f"{caption} {' '.join(str(h) for h in headers)} "
                    + " ".join(" ".join(str(c) for c in r) for r in rows if isinstance(r, list))
                )
                if not sig or sig in seen_sigs:
                    continue
                seen_sigs.add(sig)
                deduped_tables.append(table)
            content["tables"] = deduped_tables

        prose_segments = content.get("prose_segments")
        if isinstance(prose_segments, list):
            for seg in prose_segments:
                if not isinstance(seg, dict) or seg.get("type") != "text":
                    continue
                raw = str(seg.get("content", ""))
                cleaned = _LEAKED_CODE_MARKER_RE.sub("(code snippet unavailable)", raw)
                if "[code:" in cleaned.lower():
                    cleaned = re.sub(r"\[code:\s*", "(code snippet reference: ", cleaned, flags=re.IGNORECASE)
                seg["content"] = cleaned


def _inject_runtime_holistic_sections(
    rendered_pages: list[dict[str, Any]],
    plan: WikiPlan,
    entity_index: dict[str, dict],
    call_graph: dict[str, list[str]],
    domain_entities: dict | None = None,
) -> None:
    """Inject runtime agent roster + handoff diagram into home page for holistic comprehension."""
    home_page = next((p for p in rendered_pages if p.get("slug") == "home"), None)
    if not home_page:
        return
    content = home_page.get("content")
    if not isinstance(content, dict):
        return

    prose_segments = content.get("prose_segments")
    if not isinstance(prose_segments, list):
        prose_segments = []
        content["prose_segments"] = prose_segments

    # Insert near the front so Home view always exposes these sections.
    insert_at = min(len(prose_segments), 2)

    # ── Inject Runtime Agent Roster (table format) ──────────────────────
    if not any(
        isinstance(seg, dict)
        and seg.get("type") == "heading"
        and str(seg.get("text", "")).strip().lower() == "runtime agent roster"
        for seg in prose_segments
    ):
        agents = (domain_entities or {}).get("agents", [])

        if agents:
            # Build table rows: Agent | Role | Key Tools
            table_rows = []
            for ag in agents[:12]:
                name = ag.get("name", "")
                # Extract role from docstring first line or name-based heuristic
                role = (ag.get("docstring") or "").split("\n")[0].strip()
                if not role:
                    role = _infer_agent_role(name)
                tools_list = ag.get("tools", []) or []
                tools_str = ", ".join(f"`{t}`" for t in tools_list[:4]) if tools_list else "—"
                table_rows.append(f"| **{name}** | {role[:80]} | {tools_str} |")

            roster_text = (
                "| Agent | Role | Key Tools |\n"
                "|-------|------|----------|\n"
                + "\n".join(table_rows)
            )
        else:
            # Fallback: name-only list from entity_index
            names = sorted({
                str(info.get("name", ""))
                for info in entity_index.values()
                if str(info.get("name", "")).lower().endswith("agent")
            })
            if not names:
                names = [s.title for s in plan.sections if "agent" in s.title.lower()]
            roster_text = (
                "Agents detected in repository context:\n- " + "\n- ".join(names[:20])
                if names else
                "No agents matched '*Agent' naming; review section pages for runtime actors."
            )

        prose_segments.insert(insert_at, {"type": "heading", "level": 2, "text": "Runtime Agent Roster"})
        prose_segments.insert(insert_at + 1, {"type": "text", "content": roster_text})
        insert_at += 2

    # ── Inject Runtime Flow (Mermaid sequence diagram) ──────────────────
    if not any(
        isinstance(seg, dict)
        and seg.get("type") == "heading"
        and str(seg.get("text", "")).strip().lower() == "runtime flow"
        for seg in prose_segments
    ):
        agents = (domain_entities or {}).get("agents", [])
        mermaid_src = _build_agent_handoff_diagram(agents, entity_index, call_graph)

        prose_segments.insert(insert_at, {"type": "heading", "level": 2, "text": "Runtime Flow"})
        prose_segments.insert(insert_at + 1, {
            "type": "text",
            "content": "End-to-end request flow: user input → triage → specialist agent → tool execution → response.",
        })
        if mermaid_src:
            # Inject as a diagram segment so the renderer treats it as Mermaid
            prose_segments.insert(insert_at + 2, {
                "type": "diagram",
                "mermaid_source": mermaid_src,
                "caption": "Agent handoff flow — how user requests route through the system",
            })


def _infer_agent_role(name: str) -> str:
    """Infer a short role description from the agent class name."""
    mapping = {
        "triage": "Routes user requests to the appropriate specialist agent",
        "flight": "Provides flight status, delays, and connection information",
        "booking": "Handles flight bookings, rebookings, and cancellations",
        "cancellation": "Handles flight bookings, rebookings, and cancellations",
        "seat": "Manages seat assignments and special service requests",
        "faq": "Answers policy questions on baggage, compensation, and amenities",
        "refund": "Processes compensation claims and travel disruption support",
        "compensation": "Processes compensation claims and travel disruption support",
        "auth": "Handles authentication and authorization",
        "payment": "Processes payment transactions",
    }
    name_lower = name.lower()
    for keyword, role in mapping.items():
        if keyword in name_lower:
            return role
    return f"Handles {name.replace('Agent', '').replace('Handler', '').strip()} operations"


def _build_agent_handoff_diagram(
    agents: list[dict],
    entity_index: dict[str, dict],
    call_graph: dict[str, list[str]],
) -> str:
    """Build a Mermaid sequence diagram showing agent handoffs.

    Tries call_graph-based edges first; falls back to star topology from triage.
    """
    if not agents:
        return ""

    agent_names = {ag.get("name", "") for ag in agents}
    agent_qnames = {ag.get("qualified_name", ""): ag.get("name", "") for ag in agents}

    # Try to find call-graph-based handoffs between agents
    handoff_edges: list[tuple[str, str]] = []
    for qname, callees in call_graph.items():
        caller_name = agent_qnames.get(qname) or entity_index.get(qname, {}).get("name", "")
        if caller_name not in agent_names:
            continue
        for callee in callees:
            callee_name = agent_qnames.get(callee) or entity_index.get(callee, {}).get("name", "")
            if callee_name in agent_names and callee_name != caller_name:
                handoff_edges.append((caller_name, callee_name))

    # Deduplicate edges
    handoff_edges = list(dict.fromkeys(handoff_edges))

    # If no direct call graph edges, try to build from handoff_targets on agents
    if not handoff_edges:
        for ag in agents:
            src = ag.get("name", "")
            for target in (ag.get("handoff_targets") or []):
                if target in agent_names and target != src:
                    handoff_edges.append((src, target))
        handoff_edges = list(dict.fromkeys(handoff_edges))

    if len(agents) <= 1:
        return ""

    lines = ["sequenceDiagram"]
    lines.append("    participant User")
    for ag in agents[:8]:
        name = ag.get("name", "")
        short = name.replace("Agent", " Agent").replace("Handler", " Handler").strip()
        lines.append(f"    participant {name} as {short}")

    if handoff_edges:
        lines.append("    User->>+" + agents[0].get("name", "Agent") + ": request")
        seen = set()
        for src, dst in handoff_edges[:6]:
            key = (src, dst)
            if key not in seen:
                lines.append(f"    {src}->>{dst}: handoff")
                seen.add(key)
        lines.append("    " + agents[0].get("name", "Agent") + "-->>-User: response")
    else:
        # Star topology: first agent (likely Triage) routes to all others
        triage = next(
            (ag.get("name") for ag in agents if "triage" in ag.get("name", "").lower()),
            agents[0].get("name", "Agent"),
        )
        lines.append(f"    User->>+{triage}: request")
        for ag in agents[:6]:
            name = ag.get("name", "")
            if name != triage:
                lines.append(f"    {triage}->>{name}: route")
                lines.append(f"    {name}-->>User: response")
        lines.append(f"    {triage}-->>-User: consolidated response")

    return "\n".join(lines)


def _evaluate_rendered_page_quality(
    rendered_pages: list[dict[str, Any]],
    all_files: list[str],
    repo_path: str,
    entity_index: dict[str, dict],
    domain_entities: dict | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    settings = get_settings()
    warnings: list[dict[str, str]] = []
    metrics: dict[str, Any] = {}

    known_files = set(all_files)
    routes = _collect_route_paths(repo_path)
    route_validation_enabled = bool(routes)
    known_entity_names = {
        str(info.get("name", "")).lower()
        for info in entity_index.values()
        if info.get("name")
    }
    rendered_texts: dict[str, str] = {}
    avg_sentence_words: list[float] = []
    placeholders = 0
    bad_paths = 0
    bad_endpoints = 0
    auto_link_like = 0
    total_diagrams = 0
    explained_diagrams = 0
    has_runtime_roster = False
    has_runtime_flow = False

    for page in rendered_pages:
        slug = str(page.get("slug", "unknown"))
        content = page.get("content", {})
        if not isinstance(content, dict):
            continue
        text = _extract_page_text(content)
        prose_reference_text = _extract_page_text(content, include_diagram_captions=False)
        rendered_texts[slug] = text
        lower_text = text.lower()
        prose_reference_lower = prose_reference_text.lower()

        if "runtime agent roster" in lower_text:
            has_runtime_roster = True
        if "runtime flow" in lower_text or "sequence of interactions" in lower_text:
            has_runtime_flow = True

        for pattern in _PLACEHOLDER_PATTERNS:
            for _ in pattern.finditer(text):
                placeholders += 1
                warnings.append({
                    "page": slug,
                    "reason": "placeholder_leak",
                    "detail": f"Matched placeholder pattern '{pattern.pattern}'",
                })

        for path_match in _PATH_PATTERN.finditer(text):
            path_candidate = path_match.group(0)
            if path_candidate not in known_files and not (Path(repo_path) / path_candidate).exists():
                bad_paths += 1
                warnings.append({
                    "page": slug,
                    "reason": "unresolved_path_reference",
                    "detail": path_candidate[:250],
                })

        endpoint_scan_text = _URL_PATTERN.sub(" ", text)
        for endpoint_match in _ENDPOINT_PATTERN.finditer(endpoint_scan_text):
            endpoint = _normalize_endpoint_path(endpoint_match.group(0))
            if endpoint.startswith("//"):
                continue
            if endpoint.startswith("/openai/") or endpoint.startswith("/dashboard") or endpoint.startswith("/login"):
                continue
            if not _is_likely_endpoint_reference(
                endpoint_scan_text,
                endpoint_match.start(),
                endpoint_match.end(),
                endpoint,
            ):
                continue
            if not route_validation_enabled:
                continue
            if endpoint not in routes and not endpoint.startswith("/v1/"):
                bad_endpoints += 1
                warnings.append({
                    "page": slug,
                    "reason": "unresolved_endpoint_reference",
                    "detail": endpoint[:250],
                })

        sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
        if sentences:
            avg = statistics.mean(len(s.split()) for s in sentences)
            avg_sentence_words.append(avg)
            if avg > settings.wiki_quality_max_avg_sentence_words:
                warnings.append({
                    "page": slug,
                    "reason": "verbosity_high",
                    "detail": f"Average sentence length {avg:.1f} words exceeds {settings.wiki_quality_max_avg_sentence_words}",
                })

        page_diagrams = content.get("diagrams", [])
        if isinstance(page_diagrams, list):
            total_diagrams += len(page_diagrams)
            if page_diagrams:
                explained = 0
                for diagram in page_diagrams:
                    if not isinstance(diagram, dict):
                        continue
                    caption = str(diagram.get("caption", "")).strip().lower()
                    if caption and any(token in prose_reference_lower for token in caption.split()[:2]):
                        explained += 1
                interpretation_count = 0
                for seg in content.get("prose_segments", []) or []:
                    if not isinstance(seg, dict) or seg.get("type") != "text":
                        continue
                    seg_text = str(seg.get("content", "")).lower()
                    if "diagram interpretation:" in seg_text or "this diagram" in seg_text:
                        interpretation_count += 1
                explained = max(explained, min(len(page_diagrams), interpretation_count))
                explained_diagrams += explained
                if explained == 0:
                    warnings.append({
                        "page": slug,
                        "reason": "diagram_not_explained",
                        "detail": "Page has diagrams but prose does not clearly reference them.",
                    })

        for link in content.get("source_links", []) or []:
            if not isinstance(link, dict):
                continue
            name = str(link.get("name", "")).strip().lower()
            if name in {"agent", "key", "state", "data", "model", "event"} and name not in known_entity_names:
                auto_link_like += 1
                warnings.append({
                    "page": slug,
                    "reason": "ambiguous_source_link",
                    "detail": f"Ambiguous auto-link name '{name}'",
                })

    slugs = list(rendered_texts.keys())
    tokenized_texts: dict[str, set[str]] = {
        slug: _tokenize_text(rendered_texts.get(slug, "")) for slug in slugs
    }
    max_similarity = 0.0
    for i, left in enumerate(slugs):
        for right in slugs[i + 1:]:
            sim = _jaccard_similarity_from_tokens(
                tokenized_texts.get(left, set()),
                tokenized_texts.get(right, set()),
            )
            if sim > max_similarity:
                max_similarity = sim
            if sim >= settings.wiki_quality_cross_page_similarity_threshold:
                warnings.append({
                    "page": f"{left}::{right}",
                    "reason": "cross_page_duplication",
                    "detail": f"Similarity {sim:.2f} exceeds threshold {settings.wiki_quality_cross_page_similarity_threshold:.2f}",
                })

    # Home runtime sections are mandatory signals for holistic understanding.
    if not has_runtime_roster:
        warnings.append({
            "page": "home",
            "reason": "runtime_agent_roster_missing",
            "detail": "No 'Runtime Agent Roster' section detected across rendered pages.",
        })
    if not has_runtime_flow:
        warnings.append({
            "page": "home",
            "reason": "runtime_flow_missing",
            "detail": "No explicit runtime flow explanation detected across rendered pages.",
        })

    metrics["placeholders_detected"] = placeholders
    metrics["unresolved_paths_detected"] = bad_paths
    metrics["unresolved_endpoints_detected"] = bad_endpoints
    metrics["ambiguous_links_detected"] = auto_link_like
    metrics["max_cross_page_similarity"] = round(max_similarity, 3)
    metrics["avg_sentence_words"] = round(statistics.mean(avg_sentence_words), 2) if avg_sentence_words else 0.0
    metrics["diagram_coverage"] = round((explained_diagrams / total_diagrams), 3) if total_diagrams else 0.0
    metrics["runtime_agent_roster_present"] = has_runtime_roster
    metrics["runtime_flow_present"] = has_runtime_flow

    # ── Agent coverage gate: core pages should name ≥50% of domain agents ──
    if domain_entities:
        agent_names = [ag.get("name", "").lower() for ag in domain_entities.get("agents", [])]
        if agent_names:
            threshold = max(1, len(agent_names) // 2)
            pages_below_threshold = 0
            for page in rendered_pages:
                slug = str(page.get("slug", ""))
                page_type = str(page.get("page_type", ""))
                # Check home page (must introduce agents) and module/agent pages
                is_core = page_type in ("module", "home") or "agent" in slug.lower()
                if not is_core:
                    continue
                page_text = rendered_texts.get(slug, "").lower()
                if not page_text:
                    continue
                coverage = sum(1 for n in agent_names if n in page_text)
                if coverage < threshold:
                    pages_below_threshold += 1
                    warnings.append({
                        "page": slug,
                        "reason": "agent_coverage_low",
                        "detail": f"Page mentions {coverage}/{len(agent_names)} domain agents (threshold: {threshold})",
                    })
            metrics["agent_coverage_pages_below_threshold"] = pages_below_threshold
            metrics["domain_agent_count"] = len(agent_names)

    # ── Word count gate: narrative pages >1500w, reference pages >800w ──
    _REFERENCE_PAGE_TYPES = {"function_index", "api_reference", "glossary", "getting_started"}
    for page in rendered_pages:
        slug = str(page.get("slug", ""))
        page_type = str(page.get("page_type", ""))
        page_text = rendered_texts.get(slug, "")
        word_count = len(page_text.split())
        is_reference = page_type in _REFERENCE_PAGE_TYPES or slug in ("function-index", "api-reference", "glossary", "getting-started")
        limit = 800 if is_reference else 1500
        if word_count > limit:
            warnings.append({
                "page": slug,
                "reason": "word_count_high",
                "detail": f"{word_count} words exceeds {limit}-word limit for {'reference' if is_reference else 'narrative'} page",
            })

    return warnings, metrics
