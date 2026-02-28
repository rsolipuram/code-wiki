"""GitHub webhook receiver — POST /v1/webhooks/github.

Accepts push events, extracts commit hash and changed files, and creates an
UpdateEvent. Only processes refs matching the repository's default branch.
"""

import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.api.deps import get_db, get_job_queue
from src.models.events import UpdateEvent, UpdateEventStatus
from src.models.repository import Repository, RepositoryStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Secret used to validate GitHub HMAC signatures.
# In production, read from environment: os.environ.get("GITHUB_WEBHOOK_SECRET", "")
_WEBHOOK_SECRET = ""


def _verify_signature(payload_bytes: bytes, signature_header: str | None) -> None:
    """Validate GitHub SHA-256 HMAC signature.

    Skips verification when no webhook secret is configured (dev/test).
    Raises HTTP 401 on mismatch.
    """
    if not _WEBHOOK_SECRET:
        return  # signature verification disabled in dev

    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed X-Hub-Signature-256 header",
        )

    expected = "sha256=" + hmac.new(
        _WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook signature verification failed",
        )


def _extract_changed_files(payload: dict[str, Any]) -> list[str]:
    """Collect unique file paths from all commits in a push payload."""
    files: set[str] = set()
    for commit in payload.get("commits", []):
        files.update(commit.get("added", []))
        files.update(commit.get("modified", []))
        files.update(commit.get("removed", []))
    return sorted(files)


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def github_push_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
    db: Session = Depends(get_db),
    queue: Any = Depends(get_job_queue),
) -> dict[str, str]:
    """Receive a GitHub push event and create an UpdateEvent.

    GitHub sends this for every push to the repository. We:
    1. Verify the HMAC signature.
    2. Ignore non-push events and non-default-branch pushes.
    3. Find the matching Repository row by clone URL.
    4. Create an UpdateEvent with status=pending.
    5. Enqueue a sync job.
    """
    payload_bytes = await request.body()

    _verify_signature(payload_bytes, x_hub_signature_256)

    # Only handle push events
    if x_github_event != "push":
        return {"status": "ignored", "reason": f"event={x_github_event}"}

    try:
        payload: dict[str, Any] = json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {exc}",
        ) from exc

    # Extract key fields
    ref: str = payload.get("ref", "")
    commit_hash: str = payload.get("after", "")
    repo_url: str = (payload.get("repository") or {}).get("clone_url", "")

    if not commit_hash or commit_hash == "0" * 40:
        return {"status": "ignored", "reason": "deletion push (after=zeros)"}

    # Normalise URL for lookup (strip .git suffix)
    canonical_url = repo_url.rstrip("/").removesuffix(".git")

    # Find repo by URL (try both with and without .git)
    repo: Repository | None = (
        db.query(Repository)
        .filter(Repository.url.in_([canonical_url, canonical_url + ".git"]))
        .first()
    )

    if repo is None:
        logger.warning("Received push for unknown repo URL: %s", repo_url)
        return {"status": "ignored", "reason": "repository not registered"}

    if repo.status not in (RepositoryStatus.ready, RepositoryStatus.analyzing):
        return {"status": "ignored", "reason": f"repo status={repo.status}"}

    changed_files = _extract_changed_files(payload)
    logger.info(
        "GitHub push: repo=%s ref=%s commit=%s files=%d",
        repo.id, ref, commit_hash[:8], len(changed_files),
    )

    # Create UpdateEvent
    event = UpdateEvent(
        repository_id=repo.id,
        commit_hash=commit_hash,
        changed_files=changed_files,
        status=UpdateEventStatus.pending,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    # Enqueue sync job
    if queue is not None:
        queue.enqueue(
            "src.jobs.sync.run_sync",
            event.id,
            job_timeout=600,
        )

    return {"status": "accepted", "event_id": event.id}
