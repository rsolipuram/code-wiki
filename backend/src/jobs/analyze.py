"""Repository analysis background job.

Orchestrates the full pipeline:
  1. Clone/pull repository
  2. Parse code entities
  3. Run recon + facet agents (via orchestrator)
  4. Generate wiki pages
  5. Persist to PostgreSQL + Neo4j + Qdrant
  6. Update repository status
"""

import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.config import get_settings
from src.models.code_entity import CodeEntity as CodeEntityModel
from src.models.code_entity import EntityType, Module
from src.models.events import UpdateEvent, UpdateEventStatus
from src.models.repository import Repository, RepositoryStatus
from src.models.wiki import PageType, Wiki, WikiPage
from src.orchestrator.graph import run_analysis
from src.parsers.base import ParsedEntity
from src.parsers.extractor import extract_entities
from src.recon import repo_recon
from src.storage import graph_db
from src.storage.repo_cache import clone, get_commit_hash, list_files
from src.wiki.compressor import CodebaseCompressor
from src.wiki.interestingness import score_entities
from src.wiki.orchestrator import generate_module_wiki
from src.wiki.v3_pipeline import generate_wiki_v3
from src.dossier.rag_index import index_entities
from src.wiki.page_builders.home_page import build_home_page
from src.wiki.page_builders.module_page import build_module_page, slugify
from src.wiki.page_builders.special_pages import (
    build_api_reference,
    build_function_index,
    build_getting_started,
    build_glossary,
)

logger = logging.getLogger(__name__)

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}


def _emit_progress(
    session: Session,
    repo: Repository,
    step: int,
    label: str,
    detail: str,
    stats: dict,
    pipeline_start: float,
    started_at: str,
) -> None:
    """Persist pipeline progress to DB and publish to Redis for SSE consumers."""
    progress = {
        "current_step": step,
        "step_label": label,
        "step_detail": detail,
        "stats": stats,
        "started_at": started_at,
        "elapsed_seconds": round(time.monotonic() - pipeline_start, 1),
    }
    repo.progress = progress
    session.commit()

    # Dual-write: also publish to Redis for SSE streaming
    try:
        from src.api.progress_events import publish_progress
        publish_progress(str(repo.id), {"type": "step_progress", **progress})
    except Exception:
        pass  # Redis unavailable is non-fatal


def analyze_repository(repository_id: str, branch: str = "main") -> dict[str, Any]:
    """Full pipeline for a repository analysis job.

    Args:
        repository_id: UUID string of the Repository to analyze.
        branch: Git branch to analyze (default: "main").

    Returns:
        Dict with status and summary statistics.
    """
    settings = get_settings()
    engine = create_engine(settings.database_url)
    pipeline_start = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()

    # Accumulated stats dict updated throughout the pipeline
    stats: dict[str, Any] = {}

    with Session(engine) as session:
        repo = session.get(Repository, repository_id)
        if not repo:
            raise ValueError(f"Repository {repository_id} not found")

        repo_url = repo.url
        repo.status = RepositoryStatus.analyzing
        repo.progress = {
            "current_step": 1,
            "step_label": "Cloning repository",
            "step_detail": f"Cloning {repo_url}...",
            "stats": stats,
            "started_at": started_at,
            "elapsed_seconds": 0,
        }
        session.commit()

        def _progress(step: int, label: str, detail: str) -> None:
            _emit_progress(session, repo, step, label, detail, stats, pipeline_start, started_at)

        try:
            # ── Step 1: Clone / pull ────────────────────────────────────────
            t0 = time.monotonic()
            logger.info("[%s] Step 1: Cloning %s (branch=%s)", repository_id, repo_url, branch)
            local_path = clone(repo_url, branch=branch)
            commit_hash = get_commit_hash(repo_url) or "unknown"
            logger.info("[%s] Step 1 done (%.1fs): commit=%s", repository_id, time.monotonic() - t0, commit_hash[:12])
            _progress(1, "Cloning repository", f"Cloned, commit {commit_hash[:12]}")

            # ── Step 2: Recon (run early for build artifact filtering) ───────
            _progress(2, "Scanning file structure", "Scanning...")
            t0 = time.monotonic()
            logger.info("[%s] Step 2: Running reconnaissance", repository_id)
            fingerprint = repo_recon.run(str(local_path))
            stats["files_scanned"] = fingerprint.file_count
            stats["loc"] = fingerprint.loc
            stats["languages"] = fingerprint.languages[:5]
            logger.info("[%s] Step 2 done (%.1fs): %d files, %d LOC", repository_id, time.monotonic() - t0, fingerprint.file_count, fingerprint.loc)
            _progress(2, "Scanning file structure", f"{fingerprint.file_count} files, {fingerprint.loc:,} lines of code")

            # ── Step 3: Parse code entities (filtered) ───────────────────────
            _progress(3, "Parsing source files", "Parsing...")
            t0 = time.monotonic()
            logger.info("[%s] Step 3: Extracting entities", repository_id)
            entities = extract_entities(
                str(local_path),
                build_output_dirs=fingerprint.build_output_dirs,
            )
            stats["entities_found"] = len(entities)
            logger.info("[%s] Step 3 done (%.1fs): %d entities", repository_id, time.monotonic() - t0, len(entities))
            _progress(3, "Parsing source files", f"Extracted {len(entities)} entities from {fingerprint.file_count} files")

            # ── Step 4: Persist entities to PostgreSQL + vector index ────────
            _progress(4, "Persisting entities", "Saving to database...")
            t0 = time.monotonic()
            logger.info("[%s] Step 4: Persisting entities to PostgreSQL", repository_id)
            module_id = _get_or_create_wiki(session, repository_id)

            # Skip vector indexing when embedding and LLM share the same LM Studio
            # instance — loading the embedding model would evict the LLM.
            settings = get_settings()
            same_endpoint = (
                settings.embedding_base_url.rstrip("/").replace("/v1", "")
                == settings.llm_base_url.rstrip("/").replace("/v1", "")
            )
            if same_endpoint:
                logger.info("[%s] Skipping vector index — embedding and LLM share endpoint", repository_id)
                _progress(4, "Persisting entities", f"Saved {len(entities)} entities (vector index deferred)")
            else:
                _progress(4, "Persisting entities", f"Saved {len(entities)} entities; indexing vectors...")
                logger.info("[%s] Step 4: Indexing %d entities into Qdrant", repository_id, len(entities))
                try:
                    index_entities(entities, str(repo.id))
                    _progress(4, "Persisting entities", f"Indexed {len(entities)} entities")
                except Exception as vec_exc:
                    logger.warning("[%s] Vector indexing failed (non-fatal): %s", repository_id, vec_exc)
                    _progress(4, "Persisting entities", f"Saved {len(entities)} entities (vector index skipped)")
            logger.info("[%s] Step 4 done (%.1fs)", repository_id, time.monotonic() - t0)

            # ── Step 4b: Persist entities to Neo4j ───────────────────────────
            _progress(4, "Building relationship graph", "Creating nodes and edges...")
            t0 = time.monotonic()
            logger.info("[%s] Step 4b: Writing to Neo4j", repository_id)
            neo4j_stats = _write_neo4j(entities)
            stats["neo4j_nodes"] = neo4j_stats["nodes"]
            stats["neo4j_edges"] = neo4j_stats["edges"]
            stats["neo4j_unresolved"] = neo4j_stats["unresolved"]
            logger.info("[%s] Step 4b done (%.1fs)", repository_id, time.monotonic() - t0)
            _progress(4, "Building relationship graph", f"{neo4j_stats['nodes']} nodes, {neo4j_stats['edges']} edges")

            # ── Step 5: Compress codebase (shared by agents + wiki pipeline) ──
            _progress(5, "Compressing codebase", "Building code summaries...")
            t0 = time.monotonic()
            logger.info("[%s] Step 5: Compressing codebase", repository_id)
            compressed = None
            try:
                scored_entities = score_entities(entities)
                compressor = CodebaseCompressor()
                compressed = compressor.compress(str(local_path), entities, fingerprint, scored_entities)
                logger.info(
                    "[%s] Step 5 done (%.1fs): level=%s, %d key_entities, %d file_summaries",
                    repository_id, time.monotonic() - t0,
                    compressed.compression_level,
                    len(compressed.key_entities),
                    len(compressed.file_summaries),
                )
            except Exception as exc:
                logger.warning("[%s] Step 5: compressor failed (non-fatal, agents will run without): %s", repository_id, exc)

            # ── Step 6: Run facet analysis (orchestrator) ───────────────────
            _progress(6, "Running AI analysis", "Starting agents...")
            t0 = time.monotonic()
            logger.info("[%s] Step 6: Running orchestrator", repository_id)

            def _agent_progress_callback(completed: int, total: int, agent_name: str) -> None:
                stats["agents_completed"] = completed
                stats["agents_total"] = total
                _progress(6, "Running AI analysis", f"Agent {agent_name} complete ({completed}/{total})")

            dossier = run_analysis(
                str(local_path), repository_id,
                fingerprint=fingerprint,
                progress_callback=_agent_progress_callback,
                compressed=compressed,
                repo_name=repo.name or repo_url.split("/")[-1],
            )
            logger.info("[%s] Step 6 done (%.1fs)", repository_id, time.monotonic() - t0)

            # ── Step 7: Detect modules ── (now handled by V3 planner — skip) ──
            # V3 pipeline creates Module records directly from the WikiNav sections.
            stats["modules_detected"] = 0  # updated after wiki gen

            # ── Step 8: Generate wiki pages ─────────────────────────────────
            _progress(8, "Generating wiki pages", "Generating...")
            t0 = time.monotonic()
            logger.info("[%s] Step 8: Generating wiki pages (V3)", repository_id)
            wiki = session.query(Wiki).filter_by(repository_id=repository_id).first()
            if not wiki:
                wiki = Wiki(repository_id=repository_id)
                session.add(wiki)
                session.flush()

            stats["pages_generated"] = 0
            stats["pages_total"] = 0

            def _page_progress_callback(pages_done: int, page_name: str) -> None:
                stats["pages_generated"] = pages_done
                if pages_done == 0:
                    _progress(8, "Generating wiki pages", f"AI: {page_name}")
                else:
                    _progress(8, "Generating wiki pages", f"Page {pages_done}: {page_name}")

            v3_result = generate_wiki_v3(
                session=session,
                wiki=wiki,
                entities=entities,
                repo_name=repo.name or repo_url.split("/")[-1],
                repo_url=repo_url,
                repo_path=str(local_path),
                repository_id=repository_id,
                fingerprint=fingerprint,
                dossier=dossier,
                commit_hash=commit_hash,
                page_progress_callback=_page_progress_callback,
                compressed=compressed,
            )
            pages_created = int(v3_result.get("pages_created", 0))
            generation_warnings = v3_result.get("generation_warnings", []) or []
            quality_metrics = v3_result.get("quality_metrics", {}) or {}

            stats["modules_detected"] = quality_metrics.get("sections_planned", 0)
            stats["pages_generated"] = pages_created
            stats["pages_total"] = pages_created
            if generation_warnings:
                stats["warnings_count"] = len(generation_warnings)
                stats["generation_warnings"] = generation_warnings
            if quality_metrics:
                stats["quality_metrics"] = quality_metrics
            logger.info("[%s] Step 8 done (%.1fs): %d pages", repository_id, time.monotonic() - t0, pages_created)

            # ── Step 9: Finalizing ──────────────────────────────────────────
            _progress(9, "Finalizing", "Saving final state...")
            repo.status = RepositoryStatus.ready
            repo.last_analyzed_commit = commit_hash
            repo.last_analyzed_at = datetime.now(timezone.utc)
            repo.primary_languages = fingerprint.languages[:5]
            repo.size_files = fingerprint.file_count
            repo.size_lines = fingerprint.loc
            degraded_flag = False
            if generation_warnings:
                critical_warning_reasons = {
                    "placeholder_leak",
                    "runtime_agent_roster_missing",
                    "runtime_flow_missing",
                    "unresolved_path_reference",
                    "unresolved_endpoint_reference",
                }
                degraded_warnings = [
                    w for w in generation_warnings
                    if isinstance(w, dict) and str(w.get("reason", "")) in critical_warning_reasons
                ]
                degraded_flag = bool(degraded_warnings)
                repo.progress = {
                    **(repo.progress or {}),
                    "degraded": degraded_flag,
                    "warning_count": len(generation_warnings),
                    "warnings": generation_warnings,
                    "critical_warning_count": len(degraded_warnings),
                    "quality_metrics": quality_metrics,
                }
                _progress(9, "Finalizing", f"Complete with {len(generation_warnings)} warning(s)")
            else:
                _progress(9, "Finalizing", "Complete")
            session.commit()

            total_elapsed = time.monotonic() - pipeline_start
            logger.info(
                "[%s] Analysis complete in %.1fs: %d pages, %d modules, %d entities",
                repository_id, total_elapsed, pages_created, stats.get("modules_detected", 0), len(entities),
            )

            # Publish terminal SSE event
            try:
                from src.api.progress_events import publish_progress
                payload = {"type": "done", "status": "ready"}
                if generation_warnings:
                    payload["degraded"] = degraded_flag
                    payload["has_warnings"] = True
                    payload["critical_degraded"] = degraded_flag
                    payload["warning_count"] = len(generation_warnings)
                publish_progress(repository_id, payload)
            except Exception:
                pass

            return {
                "status": "completed",
                "pages_created": pages_created,
                "modules": stats.get("modules_detected", 0),
                "entities": len(entities),
                "commit_hash": commit_hash,
                "warning_count": len(generation_warnings) if generation_warnings else 0,
            }

        except Exception as exc:
            logger.error("[%s] Analysis failed: %s", repository_id, exc)
            session.rollback()
            repo.status = RepositoryStatus.error
            repo.error_message = str(exc)
            # Keep progress at the step that failed, with error detail
            if repo.progress:
                repo.progress = {
                    **repo.progress,
                    "step_detail": f"Error: {str(exc)[:200]}",
                    "elapsed_seconds": round(time.monotonic() - pipeline_start, 1),
                }
            session.commit()

            # Publish terminal error event
            try:
                from src.api.progress_events import publish_progress
                publish_progress(repository_id, {
                    "type": "done", "status": "error", "error": str(exc)[:200],
                })
            except Exception:
                pass
            raise


def _persist_modules_and_entities(
    session: Session,
    wiki_id: str,
    modules_data: list[dict],
    local_path: Path | None = None,
) -> None:
    """Persist detected modules and their code entities to PostgreSQL.

    Entity file_paths are converted to repo-relative paths when local_path is provided.
    """
    # Delete existing modules (and cascaded code_entities) before re-inserting
    existing = session.query(Module).filter_by(wiki_id=wiki_id).all()
    for m in existing:
        session.delete(m)
    session.flush()

    resolved_root = local_path.resolve() if local_path else None

    for mod in modules_data:
        module = Module(
            wiki_id=wiki_id,
            name=mod["name"],
            slug=mod["slug"],
            description=mod.get("description", ""),
            file_paths=mod["file_paths"],
            file_count=mod["file_count"],
        )
        session.add(module)
        session.flush()

        seen_qnames: set[str] = set()
        for entity in mod["entities"]:
            if entity.qualified_name in seen_qnames:
                continue
            seen_qnames.add(entity.qualified_name)

            # Convert absolute cache paths to repo-relative
            rel_path = entity.file_path
            if resolved_root:
                try:
                    rel_path = str(Path(entity.file_path).resolve().relative_to(resolved_root))
                except ValueError:
                    rel_path = entity.file_path

            db_entity = CodeEntityModel(
                module_id=module.id,
                name=entity.name,
                qualified_name=entity.qualified_name,
                entity_type=next((e for e in EntityType if e.value == entity.entity_type), EntityType.function),
                file_path=rel_path,
                line_start=entity.line_start,
                line_end=entity.line_end,
                signature=entity.signature,
                docstring=entity.docstring,
                entity_metadata=entity.entity_metadata,
            )
            session.add(db_entity)

    session.flush()


def _get_or_create_wiki(session: Session, repository_id: str) -> str | None:
    wiki = session.query(Wiki).filter_by(repository_id=repository_id).first()
    if not wiki:
        wiki = Wiki(repository_id=repository_id)
        session.add(wiki)
        session.flush()
    return str(wiki.id)


def _write_neo4j(entities: list[ParsedEntity]) -> dict[str, int]:
    """Write all entities and relationships to Neo4j.

    Builds a name→qualified_name lookup to resolve call targets that use
    short names instead of fully qualified names (fixes dangling edges).

    Returns:
        Dict with keys: nodes, edges, unresolved.
    """
    # Build lookup: short name → qualified_name for fuzzy matching
    name_to_qname: dict[str, str] = {}
    for entity in entities:
        # First-seen wins; collisions are ambiguous and skipped
        if entity.name not in name_to_qname:
            name_to_qname[entity.name] = entity.qualified_name

    nodes_created = 0
    edges_created = 0
    edges_unresolved = 0

    # Create all nodes first
    for entity in entities:
        try:
            graph_db.create_code_entity_node(
                entity_id=entity.qualified_name,
                qualified_name=entity.qualified_name,
                entity_type=entity.entity_type,
                name=entity.name,
                file_path=entity.file_path,
            )
            nodes_created += 1
        except Exception as exc:
            logger.warning("Neo4j node creation failed for %s: %s", entity.qualified_name, exc)

    # Create relationships with fuzzy name resolution
    qnames = {e.qualified_name for e in entities}
    for entity in entities:
        for callee in entity.calls:
            try:
                # Try exact match first (callee is already a qualified name)
                if callee in qnames:
                    target = callee
                elif callee in name_to_qname:
                    # Fuzzy match: short name → qualified name
                    target = name_to_qname[callee]
                else:
                    edges_unresolved += 1
                    continue

                graph_db.create_relationship(
                    from_id=entity.qualified_name,
                    to_id=target,
                    rel_type="CALLS",
                )
                edges_created += 1
            except Exception as exc:
                logger.warning("Neo4j edge creation failed for %s → %s: %s", entity.qualified_name, callee, exc)

    if edges_unresolved:
        logger.warning("Neo4j: %d call targets unresolved (no matching entity)", edges_unresolved)
    logger.info("Neo4j stats: nodes=%d, edges=%d, unresolved=%d", nodes_created, edges_created, edges_unresolved)
    return {"nodes": nodes_created, "edges": edges_created, "unresolved": edges_unresolved}


def _detect_modules(local_path: Path, entities: list[ParsedEntity], fingerprint) -> list[dict]:
    """Group entities into modules using adaptive-depth directory detection.

    Uses fingerprint.source_roots for intelligent grouping:
    - Inside source roots (e.g. src/): depth 2 → src/hooks → "hooks"
    - Outside source roots: depth 1 → "scripts", "tests"

    Post-processing merges tiny modules and splits mega-modules.
    """
    local_path = local_path.resolve()
    source_roots = set(getattr(fingerprint, "source_roots", ()) or ())
    build_dirs = set(getattr(fingerprint, "build_output_dirs", ()) or ())
    modules: dict[str, list[ParsedEntity]] = {}

    for entity in entities:
        if entity.entity_type == "module":
            continue

        try:
            rel = str(Path(entity.file_path).resolve().relative_to(local_path))
        except ValueError:
            rel = entity.file_path

        parts = Path(rel).parts
        if not parts:
            continue

        # Skip build output and metadata dirs
        if parts[0] in _SKIP_DIRS or parts[0] in build_dirs:
            continue

        module_key = _compute_module_key(parts, source_roots)
        if module_key:
            modules.setdefault(module_key, []).append(entity)

    # Post-processing: merge tiny modules into parent, split mega-modules
    total_entities = sum(len(ents) for ents in modules.values())
    result_modules: dict[str, list[ParsedEntity]] = {}

    for mod_key, mod_entities in modules.items():
        # Skip modules entirely inside build_output_dirs
        if any(mod_key.startswith(bd) for bd in build_dirs):
            continue

        # Check for mega-module (>40% of total entities) — split to depth 3
        if total_entities > 0 and len(mod_entities) > total_entities * 0.4:
            sub_groups: dict[str, list[ParsedEntity]] = {}
            for entity in mod_entities:
                try:
                    rel = str(Path(entity.file_path).resolve().relative_to(local_path))
                except ValueError:
                    rel = entity.file_path
                parts = Path(rel).parts
                # Use depth 3 for splitting, but stop before the filename when file is at depth 3
                if len(parts) >= 3:
                    depth = 2 if len(parts) == 3 else 3
                    sub_key = "/".join(parts[:depth])
                else:
                    sub_key = mod_key
                # Strip source root prefix for display
                for sr in source_roots:
                    if sub_key.startswith(sr + "/"):
                        sub_key = sub_key[len(sr) + 1:]
                        break
                sub_groups.setdefault(sub_key, []).append(entity)
            result_modules.update(sub_groups)
        else:
            result_modules[mod_key] = mod_entities

    # Merge tiny modules (<3 entities, no index file) into parent or "misc"
    final_modules: dict[str, list[ParsedEntity]] = {}
    for mod_key, mod_entities in result_modules.items():
        has_index = any(
            Path(e.file_path).stem in ("index", "__init__", "mod", "main")
            for e in mod_entities
        )
        if len(mod_entities) < 3 and not has_index and "/" in mod_key:
            parent_key = mod_key.rsplit("/", 1)[0]
            final_modules.setdefault(parent_key, []).extend(mod_entities)
        else:
            final_modules.setdefault(mod_key, []).extend(mod_entities)

    result = []
    for mod_key, mod_entities in final_modules.items():
        # Build display name: strip source root prefix
        display_name = mod_key
        for sr in source_roots:
            if display_name.startswith(sr + "/"):
                display_name = display_name[len(sr) + 1:]
                break
            if display_name == sr:
                display_name = "core"
                break

        files = list({e.file_path for e in mod_entities})[:20]
        rel_files = []
        for f in files:
            try:
                rel_files.append(str(Path(f).resolve().relative_to(local_path)))
            except ValueError:
                rel_files.append(f)

        result.append({
            "name": display_name,
            "slug": slugify(display_name),
            "entities": mod_entities,
            "file_paths": rel_files,
            "file_count": len(files),
            "description": "",
        })

    # Humanize module names for display
    _humanize_module_names(result)

    return result


def _humanize_module_names(modules: list[dict]) -> None:
    """Convert path-based module names to human-friendly display names.

    E.g. 'python-backend/airline' → 'Airline'
         'agents/triage' → 'Triage'
    Handles duplicates by adding parent context.
    """
    # Count base names to detect duplicates
    base_counts: dict[str, int] = {}
    for mod in modules:
        base = mod["name"].rsplit("/", 1)[-1]
        human = base.replace("-", " ").replace("_", " ").title()
        base_counts[human] = base_counts.get(human, 0) + 1

    for mod in modules:
        parts = mod["name"].split("/")
        base = parts[-1]
        # Strip file extension as safety net (in case a filename sneaks through as a key)
        if "." in base:
            base = Path(base).stem
        human = base.replace("-", " ").replace("_", " ").title()
        if base_counts.get(human, 0) > 1 and len(parts) > 1:
            parent = parts[-2].replace("-", " ").replace("_", " ").title()
            human = f"{parent} / {human}"
        mod["name"] = human
        # slug is already generated — keep it unchanged


def _compute_module_key(parts: tuple[str, ...], source_roots: set[str]) -> str | None:
    """Compute the module grouping key for a file path.

    Inside source roots: use depth 2 (e.g. src/hooks → hooks).
    Outside source roots: use depth 1 (e.g. scripts → scripts).
    Root-level files: group as "root".
    """
    if len(parts) < 2:
        return "root"

    # Check if first part is a source root
    if parts[0] in source_roots:
        if len(parts) >= 3:
            # depth 2 inside source root: src/hooks/useAuth.ts → "src/hooks"
            return f"{parts[0]}/{parts[1]}"
        else:
            # File directly in source root: src/index.ts → "src"
            return parts[0]

    # Outside source roots: depth 1
    return parts[0]


def _generate_all_pages_v1(
    session: Session,
    wiki: Wiki,
    entities: list[ParsedEntity],
    modules_data: list[dict],
    repo_name: str,
    repo_url: str,
    repo_path: str,
    repository_id: str,
    fingerprint,
    dossier,
    commit_hash: str,
    page_progress_callback: Optional[Callable[[int, str], None]] = None,
) -> int:
    """Generate and persist all wiki pages. Returns count of pages created."""
    pages = 0

    def _report_page(page_name: str) -> None:
        if page_progress_callback:
            page_progress_callback(pages, page_name)

    # Module pages
    module_summaries = []
    for mod in modules_data:
        try:
            wiki_content = generate_module_wiki(
                module_name=mod["name"],
                entities=mod["entities"],
                file_paths=mod["file_paths"],
                repository_id=repository_id,
                repo_path=repo_path,
                dossier=dossier,
            )
            page_content = build_module_page(
                module_name=mod["name"],
                wiki_content=wiki_content,
                entities=mod["entities"],
                file_paths=mod["file_paths"],
                commit_hash=commit_hash,
            )
            page = WikiPage(
                wiki_id=wiki.id,
                page_type=PageType.module,
                title=mod["name"].replace("_", " ").title(),
                slug=mod["slug"],
                content=page_content,
                source_files=mod["file_paths"],
                commit_hash=commit_hash,
            )
            session.add(page)
            session.flush()
            pages += 1
            _report_page(mod["name"])
            module_summaries.append({
                "name": mod["name"],
                "slug": mod["slug"],
                "description": wiki_content.get("purpose", "")[:100],
                "file_count": mod["file_count"],
            })
        except Exception as exc:
            logger.warning("Module page failed for %s: %s", mod["name"], exc)

    # Update Module DB records with AI-generated descriptions
    for summary in module_summaries:
        if summary.get("description"):
            module_record = session.query(Module).filter_by(
                wiki_id=wiki.id, slug=summary["slug"]
            ).first()
            if module_record:
                module_record.description = summary["description"]
    session.flush()

    # Special pages
    home_content = build_home_page(
        repo_name=repo_name,
        repo_url=repo_url,
        fingerprint=fingerprint,
        modules=module_summaries,
        entities=entities,
        commit_hash=commit_hash,
    )
    session.add(WikiPage(
        wiki_id=wiki.id, page_type=PageType.home, title=f"{repo_name} — Overview",
        slug="home", content=home_content, commit_hash=commit_hash,
    ))
    pages += 1
    _report_page("Home")

    try:
        gs_content = build_getting_started(
            repo_name,
            repo_path,
            fingerprint.to_dict(),
            repo_url=repo_url,
        )
        gs_content["commit_hash"] = commit_hash
        session.add(WikiPage(
            wiki_id=wiki.id, page_type=PageType.getting_started, title="Getting Started",
            slug="getting-started", content=gs_content, commit_hash=commit_hash,
        ))
        pages += 1
        _report_page("Getting Started")
    except Exception as exc:
        logger.warning("Getting started page failed: %s", exc)

    try:
        fi_content = build_function_index(entities, repo_path)
        fi_content["commit_hash"] = commit_hash
        session.add(WikiPage(
            wiki_id=wiki.id, page_type=PageType.function_index, title="Function Index",
            slug="function-index", content=fi_content, commit_hash=commit_hash,
        ))
        pages += 1
        _report_page("Function Index")
    except Exception as exc:
        logger.warning("Function index page failed: %s", exc)

    try:
        glossary_content = build_glossary(entities, repo_path)
        glossary_content["commit_hash"] = commit_hash
        session.add(WikiPage(
            wiki_id=wiki.id, page_type=PageType.glossary, title="Glossary",
            slug="glossary", content=glossary_content, commit_hash=commit_hash,
        ))
        pages += 1
        _report_page("Glossary")
    except Exception as exc:
        logger.warning("Glossary page failed: %s", exc)

    try:
        api_content = build_api_reference(entities, repo_path)
        api_content["commit_hash"] = commit_hash
        session.add(WikiPage(
            wiki_id=wiki.id, page_type=PageType.api_reference, title="API Reference",
            slug="api-reference", content=api_content, commit_hash=commit_hash,
        ))
        pages += 1
        _report_page("API Reference")
    except Exception as exc:
        logger.warning("API reference page failed: %s", exc)

    session.commit()
    return pages
