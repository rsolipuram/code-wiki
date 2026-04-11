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
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.config import get_settings
from src.models import events as _events_models  # noqa: F401
from src.models.repository import Repository, RepositoryStatus
from src.models.wiki import Wiki
from src.orchestrator.graph import run_analysis
from src.parsers.base import ParsedEntity
from src.parsers.extractor import extract_entities
from src.recon import repo_recon
from src.storage import graph_db
from src.storage.repo_cache import clone, get_commit_hash
from src.wiki.compressor import CodebaseCompressor
from src.wiki.interestingness import score_entities
from src.wiki.wiki_pipeline import generate_wiki_v3
from src.dossier.rag_index import index_entities

logger = logging.getLogger(__name__)


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
    # Ensure wiki pipeline logs (INFO) are visible in the RQ worker
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for mod in ("src.wiki.agents.content_planner", "src.wiki.wiki_pipeline", "src.wiki.compressor"):
        logging.getLogger(mod).setLevel(logging.INFO)

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
            _get_or_create_wiki(session, repository_id)

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
            index_cache = None
            try:
                # Initialise per-repo/branch artifact cache
                from src.cache.index_cache import IndexCache
                repo_name = repo.name or repo_url.split("/")[-1]
                index_cache = IndexCache(
                    repo_name=repo_name,
                    branch=branch or "main",
                )
                logger.info("[%s] IndexCache root: %s", repository_id, index_cache.root)
            except Exception as cache_exc:
                logger.warning("[%s] IndexCache init failed (non-fatal): %s", repository_id, cache_exc)
            try:
                scored_entities = score_entities(entities)
                compressor = CodebaseCompressor()
                compressed = compressor.compress(
                    str(local_path), entities, fingerprint, scored_entities,
                    cache=index_cache,
                )
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
                index_cache=index_cache,
            )
            logger.info("[%s] Step 6 done (%.1fs)", repository_id, time.monotonic() - t0)

            # ── Step 7: Detect modules ── (now handled by V3 planner — skip) ──
            # V3 pipeline creates Module records directly from the WikiNav sections.
            stats["modules_detected"] = 0  # updated after wiki gen

            # ── Step 8: Generate wiki pages ─────────────────────────────────
            _progress(8, "Generating wiki pages", "Generating...")
            t0 = time.monotonic()
            logger.info("[%s] Step 8: Generating wiki pages (V4)", repository_id)
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
