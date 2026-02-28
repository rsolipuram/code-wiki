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
from typing import Any

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
from src.wiki.orchestrator import generate_module_wiki
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

    with Session(engine) as session:
        repo = session.get(Repository, repository_id)
        if not repo:
            raise ValueError(f"Repository {repository_id} not found")

        repo_url = repo.url
        repo.status = RepositoryStatus.analyzing
        session.commit()

        try:
            # ── Step 1: Clone / pull ────────────────────────────────────────
            t0 = time.monotonic()
            logger.info("[%s] Step 1: Cloning %s (branch=%s)", repository_id, repo_url, branch)
            local_path = clone(repo_url, branch=branch)
            commit_hash = get_commit_hash(repo_url) or "unknown"
            logger.info("[%s] Step 1 done (%.1fs): commit=%s", repository_id, time.monotonic() - t0, commit_hash[:12])

            # ── Step 2: Recon (run early for build artifact filtering) ───────
            t0 = time.monotonic()
            logger.info("[%s] Step 2: Running reconnaissance", repository_id)
            fingerprint = repo_recon.run(str(local_path))
            logger.info("[%s] Step 2 done (%.1fs): %d files, %d LOC", repository_id, time.monotonic() - t0, fingerprint.file_count, fingerprint.loc)

            # ── Step 3: Parse code entities (filtered) ───────────────────────
            t0 = time.monotonic()
            logger.info("[%s] Step 3: Extracting entities", repository_id)
            entities = extract_entities(
                str(local_path),
                build_output_dirs=fingerprint.build_output_dirs,
            )
            logger.info("[%s] Step 3 done (%.1fs): %d entities", repository_id, time.monotonic() - t0, len(entities))

            # ── Step 4: Persist entities to PostgreSQL ──────────────────────
            t0 = time.monotonic()
            logger.info("[%s] Step 4: Persisting entities to PostgreSQL", repository_id)
            module_id = _get_or_create_wiki(session, repository_id)
            logger.info("[%s] Step 4 done (%.1fs)", repository_id, time.monotonic() - t0)

            # ── Step 5: Run facet analysis (orchestrator) ───────────────────
            t0 = time.monotonic()
            logger.info("[%s] Step 5: Running orchestrator", repository_id)
            dossier = run_analysis(str(local_path), repository_id, fingerprint=fingerprint)
            logger.info("[%s] Step 5 done (%.1fs)", repository_id, time.monotonic() - t0)

            # ── Step 6: Persist entities to Neo4j ──────────────────────────
            t0 = time.monotonic()
            logger.info("[%s] Step 6: Writing to Neo4j", repository_id)
            _write_neo4j(entities)
            logger.info("[%s] Step 6 done (%.1fs)", repository_id, time.monotonic() - t0)

            # ── Step 7: Detect modules ──────────────────────────────────────
            t0 = time.monotonic()
            logger.info("[%s] Step 7: Detecting modules", repository_id)
            modules_data = _detect_modules(local_path, entities, fingerprint)
            mod_names = [m["name"] for m in modules_data]
            logger.info("[%s] Step 7 done (%.1fs): %d modules — %s", repository_id, time.monotonic() - t0, len(modules_data), mod_names)

            # ── Step 8: Generate wiki pages ─────────────────────────────────
            t0 = time.monotonic()
            logger.info("[%s] Step 8: Generating wiki pages", repository_id)
            wiki = session.query(Wiki).filter_by(repository_id=repository_id).first()
            if not wiki:
                wiki = Wiki(repository_id=repository_id)
                session.add(wiki)
                session.flush()

            # Persist Module and CodeEntity records to PostgreSQL
            _persist_modules_and_entities(session, wiki.id, modules_data, local_path)

            pages_created = _generate_all_pages(
                session=session,
                wiki=wiki,
                entities=entities,
                modules_data=modules_data,
                repo_name=repo.name or repo_url.split("/")[-1],
                repo_url=repo_url,
                repo_path=str(local_path),
                repository_id=repository_id,
                fingerprint=fingerprint,
                dossier=dossier,
                commit_hash=commit_hash,
            )

            wiki.page_count = pages_created
            wiki.module_count = len(modules_data)
            logger.info("[%s] Step 8 done (%.1fs): %d pages", repository_id, time.monotonic() - t0, pages_created)

            # ── Step 9: Update repository status ───────────────────────────
            repo.status = RepositoryStatus.ready
            repo.last_analyzed_commit = commit_hash
            repo.last_analyzed_at = datetime.now(timezone.utc)
            repo.primary_languages = fingerprint.languages[:5]
            repo.size_files = fingerprint.file_count
            repo.size_lines = fingerprint.loc
            session.commit()

            total_elapsed = time.monotonic() - pipeline_start
            logger.info(
                "[%s] Analysis complete in %.1fs: %d pages, %d modules, %d entities",
                repository_id, total_elapsed, pages_created, len(modules_data), len(entities),
            )
            return {
                "status": "completed",
                "pages_created": pages_created,
                "modules": len(modules_data),
                "entities": len(entities),
                "commit_hash": commit_hash,
            }

        except Exception as exc:
            logger.error("[%s] Analysis failed: %s", repository_id, exc)
            repo.status = RepositoryStatus.error
            repo.error_message = str(exc)
            session.commit()
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


def _write_neo4j(entities: list[ParsedEntity]) -> None:
    """Write all entities and relationships to Neo4j.

    Builds a name→qualified_name lookup to resolve call targets that use
    short names instead of fully qualified names (fixes dangling edges).
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
                # Use depth 3 for splitting
                if len(parts) >= 3:
                    sub_key = "/".join(parts[:3])
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

    return result


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


def _generate_all_pages(
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
) -> int:
    """Generate and persist all wiki pages. Returns count of pages created."""
    pages = 0

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
            module_summaries.append({
                "name": mod["name"],
                "slug": mod["slug"],
                "description": wiki_content.get("purpose", "")[:100],
                "file_count": mod["file_count"],
            })
        except Exception as exc:
            logger.warning("Module page failed for %s: %s", mod["name"], exc)

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

    try:
        gs_content = build_getting_started(repo_name, repo_path, fingerprint.to_dict())
        session.add(WikiPage(
            wiki_id=wiki.id, page_type=PageType.getting_started, title="Getting Started",
            slug="getting-started", content=gs_content, commit_hash=commit_hash,
        ))
        pages += 1
    except Exception as exc:
        logger.warning("Getting started page failed: %s", exc)

    try:
        fi_content = build_function_index(entities)
        session.add(WikiPage(
            wiki_id=wiki.id, page_type=PageType.function_index, title="Function Index",
            slug="function-index", content=fi_content, commit_hash=commit_hash,
        ))
        pages += 1
    except Exception as exc:
        logger.warning("Function index page failed: %s", exc)

    try:
        glossary_content = build_glossary(entities, repo_path)
        session.add(WikiPage(
            wiki_id=wiki.id, page_type=PageType.glossary, title="Glossary",
            slug="glossary", content=glossary_content, commit_hash=commit_hash,
        ))
        pages += 1
    except Exception as exc:
        logger.warning("Glossary page failed: %s", exc)

    try:
        api_content = build_api_reference(entities)
        session.add(WikiPage(
            wiki_id=wiki.id, page_type=PageType.api_reference, title="API Reference",
            slug="api-reference", content=api_content, commit_hash=commit_hash,
        ))
        pages += 1
    except Exception as exc:
        logger.warning("API reference page failed: %s", exc)

    session.commit()
    return pages
