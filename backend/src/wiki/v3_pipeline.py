"""V3 wiki generation pipeline — replaces generate_wiki_v2().

Entry point for Step 8 of analyze.py.
Orchestrates the two-phase AI-driven wiki pipeline:
  Phase 1: Content Planner Agent → WikiNav (section list)
  Phase 2: Deep Content Agents (max 2 concurrent) → per-section markdown
  Phase 3: Tag Assembly → prose_segments[]
  Phase 4: Cross-link Resolution
  Phase 5: Reference Pages (Getting Started, Glossary, API Reference)

Module DB records come from WikiNav sections (replaces _detect_modules()).
WikiPage DB records are created from assembled sections.
"""

import logging
import time
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from src.dossier.schema import Dossier
from src.models.code_entity import Module
from src.models.wiki import PageType, Wiki, WikiPage
from src.parsers.base import ParsedEntity
from src.recon.fingerprint import RepoFingerprint
from src.wiki.compressor import CodebaseCompressor
from src.wiki.interestingness import score_entities
from src.wiki.v2_types import CompressedCodebase
from src.wiki.v3_graph import run_v3_pipeline
from src.wiki.v3_types import V3WikiState, WikiNav

logger = logging.getLogger(__name__)


def _dedupe_slug(base_slug: str, seen_slugs: set[str]) -> str:
    """Return a slug unique within the current wiki page creation pass."""
    slug = base_slug or "section"
    if slug not in seen_slugs:
        seen_slugs.add(slug)
        return slug

    i = 2
    while True:
        candidate = f"{slug}-{i}"
        if candidate not in seen_slugs:
            seen_slugs.add(candidate)
            return candidate
        i += 1


def generate_wiki_v3(
    session: Session,
    wiki: Wiki,
    entities: list[ParsedEntity],
    repo_name: str,
    repo_url: str,
    repo_path: str,
    repository_id: str,
    fingerprint: RepoFingerprint,
    dossier: Dossier,
    commit_hash: str,
    page_progress_callback: Optional[Callable[[int, str], None]] = None,
    compressed: Optional[CompressedCodebase] = None,
) -> dict[str, Any]:
    """Generate V3 wiki. Returns {pages_created, generation_warnings, quality_metrics}."""
    t_total = time.monotonic()
    pages_created = 0
    generation_warnings: list[dict] = []

    def _report(pages: int, name: str) -> None:
        if page_progress_callback:
            page_progress_callback(pages, name)

    # ── Phase 0: Compress ────────────────────────────────────────────────
    _report(0, "Compressing codebase...")
    if compressed is None:
        scored_entities = score_entities(entities)
        compressor = CodebaseCompressor()
        compressed = compressor.compress(repo_path, entities, fingerprint, scored_entities)
        logger.info("V3 Phase 0 (Compress): level=%s", compressed.compression_level)
    else:
        logger.info("V3 Phase 0 (Compress): reusing pre-run (level=%s)", compressed.compression_level)

    # Build all_files list
    resolved_root = Path(repo_path).resolve()
    all_files_set: set[str] = set()
    for e in entities:
        if e.entity_type == "module":
            continue
        rel = e.file_path
        try:
            rel = str(Path(e.file_path).resolve().relative_to(resolved_root))
        except ValueError:
            pass
        all_files_set.add(rel)
    all_files = sorted(all_files_set)

    # Serialize inputs for LangGraph state
    compressed_dict = _serialize_compressed(compressed)
    fp_dict = fingerprint.to_dict() if hasattr(fingerprint, "to_dict") else {}
    dossier_dict = dossier.to_dict() if hasattr(dossier, "to_dict") else {}

    initial_state: V3WikiState = {
        "repo_path": repo_path,
        "repo_url": repo_url,
        "repo_name": repo_name,
        "commit_hash": commit_hash,
        "repository_id": repository_id,
        "dossier": dossier_dict,
        "compressed": compressed_dict,
        "fingerprint": fp_dict,
        "entities": entities,
        "all_files": all_files,
        # Outputs (populated by pipeline)
        "wiki_nav": {},
        "deep_sections": [],
        "resolved_sections": [],
        "agent_results": [],
    }

    # ── Phase 1-5: Run LangGraph pipeline ────────────────────────────────
    _report(0, "AI: Planning wiki structure...")
    logger.info("[%s] V3 pipeline starting", repository_id)

    final_state = run_v3_pipeline(initial_state, repo_id=repository_id)

    wiki_nav_dict = final_state.get("wiki_nav") or {}
    wiki_nav = WikiNav.from_dict(wiki_nav_dict)
    resolved_sections: list[dict] = final_state.get("resolved_sections") or []
    words_by_slug = {
        str(s.get("section_slug", "")): int(s.get("word_count", 0) or 0)
        for s in (final_state.get("deep_sections") or [])
    }
    planned_section_summaries = [
        {
            "id": spec.slug,
            "title": spec.title,
            "word_count": words_by_slug.get(spec.slug, 0),
            "diagram_count": 0,
            "menu_group": spec.menu_group or "",
            "menu_label": spec.menu_label or spec.title,
        }
        for spec in wiki_nav.sections
        if spec.type != "home"
    ]
    planned_reading_order = [s["id"] for s in planned_section_summaries]

    # Fall back to deep_sections if crosslink resolver wasn't called
    if not resolved_sections:
        resolved_sections = final_state.get("deep_sections") or []

    # Merge reference pages (from deep_sections) that aren't in resolved_sections
    resolved_slugs = {s.get("section_slug") for s in resolved_sections}
    for sec in (final_state.get("deep_sections") or []):
        if sec.get("is_reference_page") and sec.get("section_slug") not in resolved_slugs:
            resolved_sections.append(sec)

    logger.info(
        "[%s] V3 pipeline complete: %d sections, %d pages",
        repository_id, len(wiki_nav.sections), len(resolved_sections),
    )

    # ── Persist ──────────────────────────────────────────────────────────
    _report(0, "Persisting wiki...")

    # Clean slate
    session.query(WikiPage).filter_by(wiki_id=wiki.id).delete()
    session.query(Module).filter_by(wiki_id=wiki.id).delete()
    session.flush()

    # Create Module records from WikiNav sections (exclude non-module pages like home)
    section_to_module: dict[str, Module] = {}
    for i, spec in enumerate(wiki_nav.sections):
        if spec.type == "home":
            continue
        mod = Module(
            wiki_id=wiki.id,
            name=spec.title,
            slug=spec.slug,
            description=spec.one_liner,
            file_paths=spec.seed_files,
            file_count=len(spec.seed_files),
            sort_order=i,
        )
        session.add(mod)
        session.flush()
        section_to_module[spec.slug] = mod

    # Reference pages (getting-started, glossary, api-reference) are WikiPages
    # but NOT Modules — they shouldn't appear in the learning path sidebar.

    # Create WikiPage records
    seen_page_slugs: set[str] = set()
    skipped_empty = 0
    for section_dict in resolved_sections:
        raw_slug = section_dict.get("section_slug", "")

        # Fix 5: Drop empty sections (but never home or reference pages)
        segments = section_dict.get("prose_segments", [])
        word_count = section_dict.get("word_count", 0)
        if not segments or word_count < 50:
            is_ref = section_dict.get("is_reference_page", False)
            is_home = raw_slug in ("home", "overview", "introduction")
            if not is_ref and not is_home:
                logger.warning(
                    "Dropping empty section %r (%d words, %d segments)",
                    raw_slug, word_count, len(segments),
                )
                skipped_empty += 1
                continue

        slug = _dedupe_slug(raw_slug, seen_page_slugs)
        title = section_dict.get("section_title", "")
        is_ref = section_dict.get("is_reference_page", False)

        page_type = _slug_to_page_type(slug, is_ref)

        page_content = section_dict.get("page_content")
        if isinstance(page_content, dict) and page_content:
            content = dict(page_content)
            content.setdefault("version", 2)
            content.setdefault("prose_segments", section_dict.get("prose_segments", []))
            content.setdefault("word_count", section_dict.get("word_count", 0))
            content.setdefault("critic_passed", section_dict.get("critic_passed", True))
            content.setdefault("section_type", "module")
            content.setdefault("related_pages", [])
        else:
            content = {
                "version": 2,
                "prose_segments": section_dict.get("prose_segments", []),
                "word_count": section_dict.get("word_count", 0),
                "critic_passed": section_dict.get("critic_passed", True),
                "section_type": "module",
                "related_pages": [],
            }

        # Planner-defined menu structure lives on home page content so frontend
        # can build grouped Learning Path without hardcoded title heuristics.
        if page_type == PageType.home:
            content["section_summaries"] = planned_section_summaries
            content["suggested_reading_order"] = planned_reading_order

        page = WikiPage(
            wiki_id=wiki.id,
            page_type=page_type,
            title=title,
            slug=slug,
            content=content,
            source_files=section_dict.get("source_files", []),
            commit_hash=commit_hash,
            summary=_extract_summary(section_dict.get("prose_segments", []), 200),
        )
        session.add(page)
        session.flush()

        # Link module → page
        mod = section_to_module.get(slug)
        if mod:
            mod.wiki_page_id = page.id

        pages_created += 1
        _report(pages_created, f"Generated {title}")

        # Warn on critic failure
        if not section_dict.get("critic_passed", True):
            generation_warnings.append({
                "page": slug,
                "reason": "critic_failed",
                "detail": f"Quality check failed after {section_dict.get('critic_retries', 0)} retries",
            })

    _validate_reference_pages(session, wiki.id, generation_warnings)

    # Update wiki counters — prune orphan modules (planned but page filtered out)
    created_page_slugs = seen_page_slugs
    for slug, mod in list(section_to_module.items()):
        if slug not in created_page_slugs:
            logger.info("Pruning orphan module %r (no page created)", slug)
            session.delete(mod)
            del section_to_module[slug]

    wiki.page_count = pages_created
    wiki.module_count = len(section_to_module)

    session.commit()

    total_elapsed = time.monotonic() - t_total
    logger.info(
        "V3 pipeline complete: %d pages, %d empty skipped, %d warnings (%.1fs)",
        pages_created, skipped_empty, len(generation_warnings), total_elapsed,
    )

    return {
        "pages_created": pages_created,
        "generation_warnings": generation_warnings,
        "quality_metrics": {
            "sections_planned": len(wiki_nav.sections),
            "sections_written": len(resolved_sections),
        },
    }


def _validate_reference_pages(session: Session, wiki_id: str, generation_warnings: list[dict]) -> None:
    required_slugs = {
        "getting-started": ("getting_started", "setup_steps"),
        "api-reference": ("api_reference", "index"),
        "function-index": ("function_index", "index"),
        "glossary": ("glossary", "terms"),
    }
    pages = session.query(WikiPage).filter_by(wiki_id=wiki_id).all()
    by_slug = {p.slug: p for p in pages}
    for slug, (expected_type, required_key) in required_slugs.items():
        page = by_slug.get(slug)
        if not page:
            generation_warnings.append({
                "page": slug,
                "reason": "missing_reference_page",
                "detail": "Required reference page missing after persist",
            })
            continue
        if str(page.page_type) != expected_type and getattr(page.page_type, "value", str(page.page_type)) != expected_type:
            generation_warnings.append({
                "page": slug,
                "reason": "reference_page_type_mismatch",
                "detail": f"Expected {expected_type}, got {page.page_type}",
            })
        content = page.content or {}
        if required_key not in content:
            generation_warnings.append({
                "page": slug,
                "reason": "reference_content_shape_mismatch",
                "detail": f"Missing required key '{required_key}' in content",
            })


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize_compressed(compressed: CompressedCodebase) -> dict:
    return {
        "repo_summary": compressed.repo_summary,
        "file_summaries": {
            k: {
                "file_path": v.file_path,
                "language": v.language,
                "line_count": v.line_count,
                "summary": v.summary,
                "entity_count": v.entity_count,
                "key_entities": v.key_entities,
                "exported_symbols": v.exported_symbols,
                "dependencies": v.dependencies,
                "nav_topic": v.nav_topic,
                "nav_role": v.nav_role,
            }
            for k, v in compressed.file_summaries.items()
        },
        "directory_summaries": {
            k: {
                "dir_path": v.dir_path,
                "file_count": v.file_count,
                "summary": v.summary,
                "child_files": v.child_files,
                "key_entities": v.key_entities,
                "nav_items": v.nav_items,
            }
            for k, v in compressed.directory_summaries.items()
        },
        "key_entities": compressed.key_entities,
        "call_graph_summary": compressed.call_graph_summary,
        "import_graph_summary": compressed.import_graph_summary,
        "compression_level": compressed.compression_level,
        "nav_plan": compressed.nav_plan,
    }


def _slug_to_page_type(slug: str, is_ref: bool) -> PageType:
    if slug == "getting-started":
        return PageType.getting_started
    if slug == "glossary":
        return PageType.glossary
    if slug == "api-reference":
        return PageType.api_reference
    if slug == "function-index":
        return PageType.function_index
    if is_ref:
        return PageType.module
    # Home section → home type
    if slug in ("home", "overview", "introduction", "getting-started"):
        return PageType.home
    return PageType.module


def _extract_summary(prose_segments: list[dict], max_chars: int) -> str:
    for seg in prose_segments:
        if seg.get("type") == "text":
            content = seg.get("content", "").strip()
            if content:
                return content[:max_chars]
    return ""
