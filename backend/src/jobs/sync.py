"""Repository sync background job.

Processes an UpdateEvent created by the GitHub webhook receiver by
superseding stale events and triggering a full V4 re-analysis for the
repository.
"""

import logging
from typing import Any

from redis import Redis
from rq import Queue
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.config import get_settings
from src.models.events import UpdateEvent, UpdateEventStatus
from src.models.repository import Repository
from src.storage.repo_cache import get_commit_hash, pull

logger = logging.getLogger(__name__)


def _get_analysis_queue() -> Queue:
    settings = get_settings()
    redis_conn = Redis.from_url(settings.redis_url)
    return Queue("analysis", connection=redis_conn)


def run_sync(event_id: str) -> dict[str, Any]:
    """Process an UpdateEvent by triggering full V4 re-analysis."""
    settings = get_settings()
    engine = create_engine(settings.database_url)

    with Session(engine) as session:
        event = session.get(UpdateEvent, event_id)
        if not event:
            raise ValueError(f"UpdateEvent {event_id} not found")

        _supersede_older_events(session, event)

        repo = session.get(Repository, event.repository_id)
        if not repo:
            logger.error("[sync %s] Repository %s not found", event_id, event.repository_id)
            event.status = UpdateEventStatus.failed
            event.error_message = "Repository not found"
            session.commit()
            return {"status": "failed", "reason": "repository not found"}

        event.status = UpdateEventStatus.processing
        session.commit()

        try:
            logger.info("[sync %s] Pulling repo %s", event_id, repo.url)
            pull(repo.url)
            commit_hash = get_commit_hash(repo.url) or event.commit_hash

            event.commit_hash = commit_hash
            event.affected_module_ids = []
            event.status = UpdateEventStatus.completed
            session.commit()

            branch = repo.branch or "main"
            queue = _get_analysis_queue()
            job_id = f"analyze-{repo.id}-sync-{event.id}"
            logger.info(
                "[sync %s] Enqueue full V4 analyze for repo=%s branch=%s commit=%s",
                event_id,
                repo.id,
                branch,
                commit_hash[:8],
            )
            queue.enqueue(
                "src.jobs.analyze.analyze_repository",
                str(repo.id),
                branch,
                job_id=job_id,
                job_timeout=-1,
            )
            return {
                "status": "completed",
                "mode": "full_reanalysis_enqueued",
                "commit_hash": commit_hash,
                "analyze_job_id": job_id,
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
