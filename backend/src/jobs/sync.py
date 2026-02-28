"""Incremental repository sync background job (T086, T089).

Processes an UpdateEvent created by the GitHub webhook receiver:
1. Supersedes older pending events for the same repository (T089).
2. Pulls the latest commit from the local cache.
3. Detects which Modules are affected by the changed files.
4. Runs partial wiki regeneration (Agent 2 + Agent 3) for each affected module.
5. Updates WikiPage.commit_hash and Repository.last_analyzed_commit.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.config import get_settings
from src.models.code_entity import CodeEntity as CodeEntityModel
from src.models.code_entity import Module
from src.models.events import UpdateEvent, UpdateEventStatus
from src.models.repository import Repository, RepositoryStatus
from src.models.wiki import Wiki, WikiPage
from src.parsers.base import ParsedEntity
from src.parsers.extractor import extract_entities
from src.storage.repo_cache import get_commit_hash, pull
from src.wiki.orchestrator import partial_regenerate
from src.wiki.page_builders.module_page import build_module_page, slugify

logger = logging.getLogger(__name__)


def run_sync(event_id: str) -> dict[str, Any]:
    """Process an UpdateEvent: detect affected modules, partially regenerate wiki.

    Args:
        event_id: UUID string of the UpdateEvent to process.

    Returns:
        Dict with status and summary statistics.
    """
    settings = get_settings()
    engine = create_engine(settings.database_url)

    with Session(engine) as session:
        event = session.get(UpdateEvent, event_id)
        if not event:
            raise ValueError(f"UpdateEvent {event_id} not found")

        # ── T089: Supersede older pending events for the same repo ───────────
        _supersede_older_events(session, event)

        repo = session.get(Repository, event.repository_id)
        if not repo:
            logger.error("[sync %s] Repository %s not found", event_id, event.repository_id)
            event.status = UpdateEventStatus.failed
            event.error_message = "Repository not found"
            session.commit()
            return {"status": "failed", "reason": "repository not found"}

        # Mark event as processing
        event.status = UpdateEventStatus.processing
        session.commit()

        try:
            # ── Step 1: Pull latest changes ──────────────────────────────────
            logger.info("[sync %s] Pulling repo %s", event_id, repo.url)
            local_path = pull(repo.url)
            commit_hash = get_commit_hash(repo.url) or event.commit_hash

            # ── Step 2: Find the wiki for this repo ──────────────────────────
            wiki = session.query(Wiki).filter_by(repository_id=repo.id).first()
            if not wiki:
                logger.warning("[sync %s] No wiki found for repo %s", event_id, repo.id)
                event.status = UpdateEventStatus.completed
                session.commit()
                return {"status": "completed", "modules_updated": 0, "reason": "no wiki"}

            # ── Step 3: Find affected modules ────────────────────────────────
            changed_files: list[str] = event.changed_files or []
            affected_modules = _find_affected_modules(session, wiki.id, changed_files)
            logger.info(
                "[sync %s] %d changed files → %d affected modules",
                event_id, len(changed_files), len(affected_modules),
            )

            # Record affected module IDs
            event.affected_module_ids = [str(m.id) for m in affected_modules]
            session.flush()

            # ── Step 4: Partial regeneration per affected module ─────────────
            modules_updated = 0
            repo_path = str(local_path)
            # Re-extract all entities from repository for context
            all_entities = _safe_extract_entities(repo_path)

            for module in affected_modules:
                try:
                    _regenerate_module(
                        session=session,
                        wiki=wiki,
                        module=module,
                        changed_files=changed_files,
                        all_entities=all_entities,
                        repo_path=repo_path,
                        repository_id=repo.id,
                        commit_hash=commit_hash,
                    )
                    modules_updated += 1
                except Exception as exc:
                    logger.warning(
                        "[sync %s] Module %s regen failed: %s", event_id, module.name, exc
                    )

            # ── Step 5: Update wiki version + repo commit ────────────────────
            wiki.version = (wiki.version or 1) + 1
            repo.last_analyzed_commit = commit_hash
            repo.last_analyzed_at = datetime.now(timezone.utc)

            event.status = UpdateEventStatus.completed
            session.commit()

            logger.info(
                "[sync %s] Completed: %d/%d modules updated, commit=%s",
                event_id, modules_updated, len(affected_modules), commit_hash[:8],
            )
            return {
                "status": "completed",
                "modules_updated": modules_updated,
                "changed_files": len(changed_files),
                "commit_hash": commit_hash,
            }

        except Exception as exc:
            logger.error("[sync %s] Sync failed: %s", event_id, exc)
            event.status = UpdateEventStatus.failed
            event.error_message = str(exc)[:1000]
            session.commit()
            raise


def _supersede_older_events(session: Session, current_event: UpdateEvent) -> None:
    """Mark all older pending/processing events for the same repo as superseded.

    This ensures we never run duplicate syncs for the same repository when
    multiple webhooks arrive in quick succession.
    """
    older = (
        session.query(UpdateEvent)
        .filter(
            UpdateEvent.repository_id == current_event.repository_id,
            UpdateEvent.id != current_event.id,
            UpdateEvent.status.in_([UpdateEventStatus.pending, UpdateEventStatus.processing]),
        )
        .all()
    )
    for evt in older:
        logger.info(
            "Superseding event %s (status=%s) for repo %s",
            evt.id, evt.status, evt.repository_id,
        )
        evt.status = UpdateEventStatus.superseded
    if older:
        session.flush()


def _find_affected_modules(
    session: Session, wiki_id: str, changed_files: list[str]
) -> list[Module]:
    """Return modules whose file_paths overlap with the changed files list.

    Falls back to all modules when changed_files is empty (e.g. manual refresh).
    """
    all_modules = session.query(Module).filter_by(wiki_id=wiki_id).all()

    if not changed_files:
        return all_modules

    changed_set = set(changed_files)
    affected: list[Module] = []
    for module in all_modules:
        module_files = set(module.file_paths or [])
        if module_files & changed_set:
            affected.append(module)

    return affected


def _safe_extract_entities(repo_path: str) -> list[ParsedEntity]:
    """Extract entities from the repository, returning empty list on failure."""
    try:
        return extract_entities(repo_path)
    except Exception as exc:
        logger.warning("Entity extraction failed: %s", exc)
        return []


def _regenerate_module(
    session: Session,
    wiki: Wiki,
    module: Module,
    changed_files: list[str],
    all_entities: list[ParsedEntity],
    repo_path: str,
    repository_id: str,
    commit_hash: str,
) -> None:
    """Run partial wiki regen for one module and update the WikiPage in DB."""
    # Filter entities relevant to this module's file paths
    module_file_set = set(module.file_paths or [])
    local_path = Path(repo_path)

    module_entities = [
        e for e in all_entities
        if _entity_in_module(e.file_path, module_file_set, local_path)
    ]

    # Identify changed entity names (those whose files changed)
    changed_entity_names = [
        e.name for e in module_entities
        if _file_is_changed(e.file_path, changed_files, local_path)
    ]

    # Run the 3-agent partial regeneration
    wiki_content = partial_regenerate(
        module_name=module.name,
        changed_entity_names=changed_entity_names,
        all_entities=module_entities,
        file_paths=module.file_paths or [],
        repository_id=repository_id,
        repo_path=repo_path,
    )

    page_content = build_module_page(
        module_name=module.name,
        wiki_content=wiki_content,
        entities=module_entities,
        file_paths=module.file_paths or [],
        commit_hash=commit_hash,
    )

    # Update or create the WikiPage
    slug = module.slug or slugify(module.name)
    page = session.query(WikiPage).filter_by(wiki_id=wiki.id, slug=slug).first()
    if page:
        page.content = page_content
        page.commit_hash = commit_hash
    else:
        page = WikiPage(
            wiki_id=wiki.id,
            slug=slug,
            title=module.name.replace("_", " ").title(),
            content=page_content,
            source_files=module.file_paths,
            commit_hash=commit_hash,
        )
        session.add(page)

    session.flush()
    logger.info("Regenerated wiki page for module %s (commit %s)", module.name, commit_hash[:8])


def _entity_in_module(
    file_path: str | None, module_files: set[str], local_path: Path
) -> bool:
    """Return True if a file_path belongs to a module's file set."""
    if not file_path:
        return False
    try:
        rel = str(Path(file_path).relative_to(local_path))
    except ValueError:
        rel = file_path
    return rel in module_files or file_path in module_files


def _file_is_changed(
    file_path: str | None, changed_files: list[str], local_path: Path
) -> bool:
    """Return True if an entity's file is in the changed_files list."""
    if not file_path:
        return False
    try:
        rel = str(Path(file_path).relative_to(local_path))
    except ValueError:
        rel = file_path
    return rel in changed_files or file_path in changed_files
