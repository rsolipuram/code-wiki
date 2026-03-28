"""Agent graph utilities shared by V3 wiki pipeline agents."""

import logging
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Set by run_v3_pipeline() before graph execution.
_current_repo_id: Optional[str] = None
_progress_activity_hook: Optional[Callable[[], None]] = None


def configure_progress_reporting(
    repo_id: Optional[str],
    on_activity: Optional[Callable[[], None]] = None,
) -> None:
    """Configure where agent progress events are published.

    Args:
        repo_id: Repository ID for progress stream events.
        on_activity: Optional callback invoked whenever an agent reports progress.
    """
    global _current_repo_id, _progress_activity_hook
    _current_repo_id = repo_id
    _progress_activity_hook = on_activity


def report_agent_progress(
    agent_name: str,
    status: str,
    detail: str = "",
    mark_activity: bool = True,
) -> None:
    """Publish an agent-level progress event to Redis.

    Called by agent nodes at start and end of execution.
    """
    if mark_activity and _progress_activity_hook:
        _progress_activity_hook()
    if not _current_repo_id:
        return
    try:
        from src.api.progress_events import publish_progress
        publish_progress(_current_repo_id, {
            "type": "agent_progress",
            "agent": agent_name,
            "status": status,
            "detail": detail,
            "timestamp": time.time(),
        })
    except Exception:
        logger.debug("Failed to publish agent progress for %s", agent_name, exc_info=True)
