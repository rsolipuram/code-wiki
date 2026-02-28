"""Git repository cache operations using GitPython."""

import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from git import GitCommandError, InvalidGitRepositoryError, Repo

from src.config import get_settings

logger = logging.getLogger(__name__)

_URL_PATTERN = re.compile(r"^https?://[^\s/$.?#].[^\s]*$")


def _cache_path(url: str) -> Path:
    """Derive a stable filesystem path for a given URL."""
    safe = re.sub(r"[^\w\-]", "_", url)[:120]
    path = Path(get_settings().repo_cache_dir) / safe
    logger.debug("Cache path for %s → %s", url, path)
    return path


def validate_url(url: str) -> None:
    """Raise ValueError if URL is not a valid-looking HTTP(S) URL."""
    if not _URL_PATTERN.match(url):
        raise ValueError(f"Invalid repository URL: {url!r}")


def clone(url: str, branch: Optional[str] = None) -> Path:
    """Clone a repository to the local cache directory.

    Returns the local path. If already cloned, performs a pull instead.
    """
    validate_url(url)
    path = _cache_path(url)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        return pull(url, branch=branch)

    logger.info("Cloning %s → %s", url, path)
    t0 = time.monotonic()
    try:
        Repo.clone_from(url, str(path), depth=None)
    except GitCommandError as exc:
        logger.error("Clone failed for %s: %s", url, exc)
        raise RuntimeError(f"Failed to clone {url!r}: {exc}") from exc

    elapsed = time.monotonic() - t0
    logger.info("Clone success: %s (%.1fs)", path, elapsed)

    if branch:
        try:
            repo = Repo(str(path))
            repo.git.checkout(branch)
            logger.info("Checked out branch %s", branch)
        except GitCommandError as exc:
            logger.warning("Branch checkout failed for %s: %s", branch, exc)

    return path


def pull(url: str, branch: Optional[str] = None) -> Path:
    """Pull latest changes for an already-cloned repository."""
    path = _cache_path(url)
    logger.info("Pulling latest for %s", url)
    t0 = time.monotonic()
    try:
        repo = Repo(str(path))
        if branch:
            repo.git.checkout(branch)
            logger.info("Checked out branch %s", branch)
        origin = repo.remotes.origin
        origin.pull()
    except (InvalidGitRepositoryError, GitCommandError) as exc:
        logger.error("Pull failed for %s: %s", url, exc)
        raise RuntimeError(f"Failed to pull {url!r}: {exc}") from exc
    elapsed = time.monotonic() - t0
    logger.info("Pull success: %s (%.1fs)", path, elapsed)
    return path


def get_commit_hash(url: str) -> Optional[str]:
    """Return the current HEAD commit SHA for a cached repository."""
    path = _cache_path(url)
    if not path.exists():
        return None
    try:
        repo = Repo(str(path))
        sha = repo.head.commit.hexsha
        logger.debug("HEAD commit for %s: %s", url, sha[:12])
        return sha
    except Exception:
        logger.warning("Failed to get commit hash for %s", url)
        return None


def list_files(url: str, extensions: Optional[list[str]] = None) -> list[str]:
    """List all tracked files in the cached repository.

    Args:
        url: Repository URL.
        extensions: Optional list of extensions to filter by (e.g. ['.py', '.ts']).

    Returns:
        List of relative file paths (POSIX format).
    """
    path = _cache_path(url)
    try:
        repo = Repo(str(path))
        files = [item.a_path for item in repo.index.diff(None)] + [
            e[0] for e in repo.index.entries.keys()
        ]
        # Deduplicate and optionally filter
        seen: set[str] = set()
        result: list[str] = []
        for f in files:
            if f in seen:
                continue
            seen.add(f)
            if extensions is None or any(f.endswith(ext) for ext in extensions):
                result.append(f)
        return result
    except (InvalidGitRepositoryError, Exception):
        # Fallback: walk filesystem
        root = Path(str(path))
        result = []
        for p in root.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(root))
                if extensions is None or any(rel.endswith(ext) for ext in extensions):
                    result.append(rel)
        return result
