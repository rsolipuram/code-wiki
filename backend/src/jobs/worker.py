"""RQ worker and queue setup for long-running repository analysis jobs."""

import logging
from typing import Any, Callable, Optional

import redis as redis_lib
from rq import Queue, Retry, Worker
from rq.job import Job

from src.config import get_settings

logger = logging.getLogger(__name__)

# 15-minute timeout per job (SC-001: 50k LOC in < 15 min)
JOB_TIMEOUT = 15 * 60  # seconds
QUEUE_NAME = "code-wiki"


def get_connection() -> redis_lib.Redis:  # type: ignore[type-arg]
    settings = get_settings()
    return redis_lib.from_url(settings.redis_url)


def get_queue() -> Queue:
    return Queue(QUEUE_NAME, connection=get_connection(), default_timeout=JOB_TIMEOUT)


def enqueue(
    func: Callable,  # type: ignore[type-arg]
    *args: Any,
    job_id: Optional[str] = None,
    **kwargs: Any,
) -> Job:
    """Enqueue a background job.

    Args:
        func: The Python callable to execute.
        *args: Positional arguments forwarded to func.
        job_id: Optional stable job ID (used to check status later).
        **kwargs: Keyword arguments forwarded to func.

    Returns:
        The RQ Job object (use job.get_status() to poll).
    """
    queue = get_queue()
    job = queue.enqueue(
        func,
        *args,
        job_id=job_id,
        timeout=JOB_TIMEOUT,
        retry=Retry(max=2, intervals=[30, 60]),
        kwargs=kwargs,
    )
    logger.info("Enqueued job %s → %s", job.id, func.__name__)
    return job


def get_job_status(job_id: str) -> dict[str, Any]:
    """Return status dict for a job.

    Returns:
        Dict with 'status' key (queued | started | finished | failed | unknown)
        and optional 'result' or 'error'.
    """
    try:
        job = Job.fetch(job_id, connection=get_connection())
        status = job.get_status().value if job.get_status() else "unknown"
        result: dict[str, Any] = {"status": status}
        if status == "finished":
            result["result"] = job.result
        elif status == "failed":
            result["error"] = str(job.latest_result().exc_string) if job.latest_result() else None
        return result
    except Exception:
        return {"status": "unknown"}


def start_worker() -> None:
    """Start an RQ worker (blocks until interrupted). Used as entrypoint."""
    conn = get_connection()
    worker = Worker([QUEUE_NAME], connection=conn)
    worker.work()
