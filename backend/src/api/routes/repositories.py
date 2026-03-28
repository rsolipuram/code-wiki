"""Repository management endpoints."""

import json
import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from rq import Queue
from rq.job import Job
from rq.exceptions import NoSuchJobError
from sqlalchemy.orm import Session

from src.api.deps import get_db, get_job_queue
from src.api.progress_events import subscribe_progress
from src.api.schemas.common import Pagination
from src.api.schemas.repositories import (
    RepositoryCreate,
    RepositoryListResponse,
    RepositoryResponse,
    UpdateEventResponse,
)
from src.models.events import UpdateEvent, UpdateEventStatus
from src.models.repository import Repository, RepositoryStatus

router = APIRouter(prefix="/repositories", tags=["repositories"])

# Simple URL validation — must look like a Git hosting URL
_URL_RE = re.compile(
    r"^https?://(github\.com|gitlab\.com|bitbucket\.org)/[\w.-]+/[\w.-]+(\.git)?/?$"
)


def _parse_owner_name(url: str) -> tuple[str, str]:
    """Extract owner and repo name from a hosting URL."""
    parts = url.rstrip("/").rstrip(".git").split("/")
    name = parts[-1] if parts else ""
    owner = parts[-2] if len(parts) >= 2 else ""
    return owner, name


def _status_str(value: object) -> str:
    """Return enum/string status as a plain string."""
    return str(getattr(value, "value", value))


def _repo_to_response(repo: Repository) -> RepositoryResponse:
    return RepositoryResponse(
        id=UUID(repo.id),
        url=repo.url,
        name=repo.name or "",
        owner=repo.owner or "",
        primary_languages=repo.primary_languages or [],
        size_lines=repo.size_lines,
        size_files=repo.size_files,
        last_analyzed_commit=repo.last_analyzed_commit,
        last_analyzed_at=repo.last_analyzed_at,
        branch=repo.branch,
        status=_status_str(repo.status),
        error_message=repo.error_message,
        progress=repo.progress,
        access_level="public",
        created_at=repo.created_at,
        updated_at=repo.updated_at,
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=RepositoryResponse)
async def create_repository(
    body: RepositoryCreate,
    db: Session = Depends(get_db),
    queue: Queue = Depends(get_job_queue),
) -> RepositoryResponse:
    """Submit a repository URL for analysis and wiki generation."""
    if not _URL_RE.match(body.url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_URL", "message": "URL must be a public GitHub/GitLab/Bitbucket repository"},
        )

    # If already submitted, return the existing repo so the frontend can redirect
    existing = db.query(Repository).filter_by(url=body.url).first()
    if existing:
        return _repo_to_response(existing)

    owner, name = _parse_owner_name(body.url)
    repo = Repository(url=body.url, name=name, owner=owner, branch=body.branch, status=RepositoryStatus.pending)
    db.add(repo)
    db.commit()
    db.refresh(repo)

    # Enqueue background analysis job
    queue.enqueue(
        "src.jobs.analyze.analyze_repository",
        repo.id,
        repo.branch or "main",
        job_id=f"analyze-{repo.id}",
        job_timeout=-1,  # No timeout — let it run as long as there's progress
    )

    return _repo_to_response(repo)


@router.get("", response_model=RepositoryListResponse)
async def list_repositories(
    repo_status: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> RepositoryListResponse:
    """List repositories with optional status filter and pagination."""
    q = db.query(Repository)
    if repo_status:
        q = q.filter(Repository.status == repo_status)

    total = q.count()
    repos = q.offset((page - 1) * limit).limit(limit).all()

    return RepositoryListResponse(
        repositories=[_repo_to_response(r) for r in repos],
        pagination=Pagination(page=page, per_page=limit, total=total, pages=max(1, (total + limit - 1) // limit)),
    )


@router.get("/{repository_id}", response_model=RepositoryResponse)
async def get_repository(
    repository_id: UUID,
    db: Session = Depends(get_db),
) -> RepositoryResponse:
    """Get repository details."""
    repo = db.get(Repository, str(repository_id))
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    return _repo_to_response(repo)


@router.get("/{repository_id}/status")
async def get_repository_status(
    repository_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    """Return current analysis status and recent update events for a repository.

    Used by the frontend Progress page to poll until analysis is complete.
    """
    repo = db.get(Repository, str(repository_id))
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    # Most recent update event
    latest_event = (
        db.query(UpdateEvent)
        .filter_by(repository_id=str(repository_id))
        .order_by(UpdateEvent.created_at.desc())  # type: ignore[attr-defined]
        .first()
    )

    return {
        "id": str(repo.id),
        "status": _status_str(repo.status),
        "error_message": repo.error_message,
        "progress": repo.progress,
        "last_analyzed_commit": repo.last_analyzed_commit,
        "last_analyzed_at": repo.last_analyzed_at.isoformat() if repo.last_analyzed_at else None,
        "latest_event": {
            "id": latest_event.id,
            "status": _status_str(latest_event.status),
            "commit_hash": latest_event.commit_hash,
            "changed_files_count": len(latest_event.changed_files or []),
            "affected_modules_count": len(latest_event.affected_module_ids or []),
            "error_message": latest_event.error_message,
        } if latest_event else None,
    }


@router.get("/{repository_id}/progress/stream")
async def stream_progress(
    repository_id: UUID,
    db: Session = Depends(get_db),
):
    """SSE endpoint streaming real-time pipeline progress."""
    repo = db.get(Repository, str(repository_id))
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    async def event_generator():
        # Send initial state from DB (catch-up for late joiners)
        if repo.progress:
            yield f"data: {json.dumps(repo.progress)}\n\n"

        # If already complete/error, send terminal event and close
        if repo.status in (RepositoryStatus.ready, RepositoryStatus.error):
            yield f"data: {json.dumps({'type': 'done', 'status': _status_str(repo.status)})}\n\n"
            return

        # Subscribe to Redis pub/sub for live events
        async for event in subscribe_progress(str(repository_id)):
            if event is None:
                # Keepalive comment — keeps connection alive through proxies
                yield ": keepalive\n\n"
                continue
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("type") == "done":
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository(
    repository_id: UUID,
    db: Session = Depends(get_db),
) -> None:
    """Remove a repository and all associated data."""
    repo = db.get(Repository, str(repository_id))
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    db.delete(repo)
    db.commit()


@router.post(
    "/{repository_id}/refresh",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UpdateEventResponse,
)
async def refresh_repository(
    repository_id: UUID,
    db: Session = Depends(get_db),
    queue: Queue = Depends(get_job_queue),
) -> UpdateEventResponse:
    """Manually trigger a repository re-analysis."""
    repo = db.get(Repository, str(repository_id))
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    commit_hash = repo.last_analyzed_commit or "HEAD"
    event = UpdateEvent(
        repository_id=str(repository_id),
        commit_hash=commit_hash,
        status=UpdateEventStatus.pending,
    )
    db.add(event)
    repo.status = RepositoryStatus.pending
    repo.error_message = None
    repo.progress = {}
    db.commit()
    db.refresh(event)

    queue.enqueue(
        "src.jobs.analyze.analyze_repository",
        str(repository_id),
        repo.branch or "main",
        job_id=f"analyze-{repository_id}-refresh-{event.id}",
        job_timeout=-1,  # No timeout
    )
    # Best-effort cleanup of legacy stuck refresh job IDs from previous runs.
    # They can block queue accounting and cause confusing "busy" worker state.
    legacy_job_id = f"analyze-{repository_id}-refresh"
    try:
        legacy_job = Job.fetch(legacy_job_id, connection=queue.connection)  # type: ignore[arg-type]
        if legacy_job and legacy_job.get_status(refresh=True) == "started":
            legacy_job.cancel()
            legacy_job.delete()
    except NoSuchJobError:
        pass

    return UpdateEventResponse(
        id=UUID(event.id),
        repository_id=UUID(event.repository_id),
        commit_hash=event.commit_hash,
        changed_files=event.changed_files or [],
        affected_module_ids=[],
        status=_status_str(event.status),
        started_at=None,
        completed_at=None,
        error_message=None,
    )
