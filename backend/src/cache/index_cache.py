"""Persistent artifact cache for the wiki compression pipeline.

Stores per-repo/per-branch file summaries, directory summaries, and
consolidated artifacts so that re-analysis skips redundant LLM calls
when source files haven't changed.

Layout on disk::

    {data_dir}/index/{safe_repo_name}/{branch}/
    ├── _manifest.json
    ├── _fingerprint.json
    ├── _compressed.json
    ├── _wiki_nav.json
    ├── _top_entities.json
    └── src/
        └── auth/
            ├── _dir.json            # DirectorySummary
            ├── provider.py.json     # FileSummary
            └── middleware.py.json
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Version constants ────────────────────────────────────────────────────────
SCHEMA_VERSION = "1.0"
FILE_PROMPT_VERSION = "compress-file-v1"
DIR_PROMPT_VERSION = "compress-dir-v1"

# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_name(name: str) -> str:
    """Sanitize a repo/branch name for use as a directory component.

    Consistent with ``repo_cache.py`` and ``serializer.py``.
    """
    return re.sub(r"[^\w\-]", "_", name)[:120]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, data: Any) -> None:
    """Write *data* as JSON atomically via a temp file + ``os.replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create temp file in same directory so os.replace is same-filesystem.
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp, str(path))
    except BaseException:
        # Clean up the temp file if anything goes wrong.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> dict | None:
    """Read a JSON file, returning *None* on any failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _make_cache_meta(
    *,
    content_hash: str = "",
    model: str = "",
    prompt_version: str = "",
    generator: str = "index_cache",
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "prompt_version": prompt_version,
        "model": model,
        "content_hash": content_hash,
        "created_at": _utcnow_iso(),
        "generator": generator,
    }


# ── CacheDiff ────────────────────────────────────────────────────────────────

@dataclass
class CacheDiff:
    """Result of comparing manifest against current file hashes."""

    hits: list[str]
    misses: list[str]
    stale: list[str]


# ── IndexCache ───────────────────────────────────────────────────────────────

class IndexCache:
    """Per-repo/per-branch artifact cache.

    Parameters
    ----------
    repo_name:
        Human-readable repo name (e.g. ``"openai-agents-python"``).
    branch:
        Git branch name (e.g. ``"main"``).
    data_dir:
        Root data directory.  When *None*, resolved from
        ``get_settings().data_dir``.
    """

    def __init__(
        self,
        repo_name: str,
        branch: str,
        data_dir: str | None = None,
    ) -> None:
        if data_dir is None:
            from src.config import get_settings
            data_dir = get_settings().resolved_data_dir
        self._root = (
            Path(data_dir) / "index" / _safe_name(repo_name) / _safe_name(branch)
        )
        self._root.mkdir(parents=True, exist_ok=True)
        logger.debug("IndexCache root: %s", self._root)

    @property
    def root(self) -> Path:
        return self._root

    # ── Manifest ─────────────────────────────────────────────────────────

    def load_manifest(self) -> dict | None:
        return _read_json(self._root / "_manifest.json")

    def save_manifest(self, manifest: dict) -> None:
        _atomic_write_json(self._root / "_manifest.json", manifest)

    # ── File summaries ───────────────────────────────────────────────────

    def _file_cache_path(self, rel_path: str) -> Path:
        """Map a repo-relative path to its cache JSON location.

        Validates that the resolved path stays within the cache root to
        prevent path-traversal attacks.
        """
        candidate = (self._root / (rel_path + ".json")).resolve()
        if not candidate.is_relative_to(self._root.resolve()):
            raise ValueError(f"Path traversal detected in cache path: {rel_path!r}")
        return candidate

    def get_file_summary(self, rel_path: str) -> dict | None:
        data = _read_json(self._file_cache_path(rel_path))
        if data is None:
            return None
        meta = data.get("_cache_meta", {})
        if meta.get("schema_version") != SCHEMA_VERSION:
            logger.debug("Schema mismatch for %s — treating as miss", rel_path)
            return None
        if meta.get("prompt_version") != FILE_PROMPT_VERSION:
            logger.debug("Prompt version mismatch for %s — treating as miss", rel_path)
            return None
        return data

    def put_file_summary(
        self,
        rel_path: str,
        summary: dict,
        content_hash: str,
        model: str,
        prompt_version: str = FILE_PROMPT_VERSION,
    ) -> None:
        payload = {
            **summary,
            "_cache_meta": _make_cache_meta(
                content_hash=content_hash,
                model=model,
                prompt_version=prompt_version,
            ),
        }
        _atomic_write_json(self._file_cache_path(rel_path), payload)

    # ── Directory summaries ──────────────────────────────────────────────

    def _dir_cache_path(self, dir_path: str) -> Path:
        """Map a directory path to its cache JSON location.

        Validates that the resolved path stays within the cache root.
        """
        candidate = (self._root / dir_path / "_dir.json").resolve()
        if not candidate.is_relative_to(self._root.resolve()):
            raise ValueError(f"Path traversal detected in dir cache path: {dir_path!r}")
        return candidate

    def get_dir_summary(self, dir_path: str) -> dict | None:
        data = _read_json(self._dir_cache_path(dir_path))
        if data is None:
            return None
        meta = data.get("_cache_meta", {})
        if meta.get("schema_version") != SCHEMA_VERSION:
            return None
        if meta.get("prompt_version") != DIR_PROMPT_VERSION:
            return None
        return data

    def put_dir_summary(
        self,
        dir_path: str,
        summary: dict,
        child_hashes: dict[str, str],
        model: str,
        prompt_version: str = DIR_PROMPT_VERSION,
    ) -> None:
        payload = {
            **summary,
            "_cache_meta": _make_cache_meta(
                content_hash=hashlib.sha256(
                    json.dumps(child_hashes, sort_keys=True).encode()
                ).hexdigest(),
                model=model,
                prompt_version=prompt_version,
            ),
            "_child_hashes": child_hashes,
        }
        _atomic_write_json(self._dir_cache_path(dir_path), payload)

    # ── Compressed (whole-repo artifact) ─────────────────────────────────

    def get_compressed(self) -> dict | None:
        return _read_json(self._root / "_compressed.json")

    def put_compressed(self, data: dict) -> None:
        payload = {
            **data,
            "_cache_meta": _make_cache_meta(generator="compressor"),
        }
        _atomic_write_json(self._root / "_compressed.json", payload)

    # ── Wiki nav ─────────────────────────────────────────────────────────

    def get_wiki_nav(self) -> dict | None:
        return _read_json(self._root / "_wiki_nav.json")

    def put_wiki_nav(self, data: dict, input_fingerprint: str = "") -> None:
        payload = {
            **data,
            "_cache_meta": _make_cache_meta(
                content_hash=input_fingerprint,
                generator="nav_consolidator",
            ),
        }
        _atomic_write_json(self._root / "_wiki_nav.json", payload)

    # ── Top entities ─────────────────────────────────────────────────────

    def get_top_entities(self) -> dict | None:
        return _read_json(self._root / "_top_entities.json")

    def put_top_entities(self, data: list[dict]) -> None:
        payload = {
            "entities": data,
            "_cache_meta": _make_cache_meta(generator="entity_scorer"),
        }
        _atomic_write_json(self._root / "_top_entities.json", payload)

    # ── Fingerprint ──────────────────────────────────────────────────────

    def get_fingerprint(self) -> dict | None:
        return _read_json(self._root / "_fingerprint.json")

    def put_fingerprint(self, data: dict) -> None:
        payload = {
            **data,
            "_cache_meta": _make_cache_meta(generator="repo_recon"),
        }
        _atomic_write_json(self._root / "_fingerprint.json", payload)

    # ── Diff / invalidation ──────────────────────────────────────────────

    def diff_against_tree(self, file_hashes: dict[str, str]) -> CacheDiff:
        """Compare a manifest of ``{rel_path: content_hash}`` against cache.

        Returns a :class:`CacheDiff` with hits (cache valid), misses (need
        LLM), and stale (cached but no longer in source tree).
        """
        manifest = self.load_manifest() or {}
        cached_hashes: dict[str, str] = manifest.get("file_hashes", {})

        hits: list[str] = []
        misses: list[str] = []

        for path, current_hash in file_hashes.items():
            if cached_hashes.get(path) == current_hash:
                # Hash matches — but also verify the cache file actually exists
                if self._file_cache_path(path).exists():
                    hits.append(path)
                else:
                    misses.append(path)
            else:
                misses.append(path)

        stale = [p for p in cached_hashes if p not in file_hashes]

        return CacheDiff(hits=hits, misses=misses, stale=stale)

    def cleanup_stale(self, stale_paths: list[str]) -> int:
        """Remove cache files for paths no longer in the source tree.

        Returns the number of files removed.
        """
        removed = 0
        for rel_path in stale_paths:
            try:
                fp = self._file_cache_path(rel_path)
            except ValueError:
                logger.warning("Skipping stale cleanup for invalid path: %s", rel_path)
                continue
            if fp.exists():
                try:
                    fp.unlink()
                    removed += 1
                except OSError as exc:
                    logger.warning("Failed to remove stale cache %s: %s", fp, exc)
        if removed:
            logger.info("Cleaned up %d stale cache files", removed)
        return removed
