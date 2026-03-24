"""Dossier serializer — writes the full populated Dossier to disk as JSON.

Called after all agents complete, before wiki generation. Produces:
    cache/wiki_artifacts/{repo_name}/_dossier.json

This file is for inspection/debugging only — it is not used by any pipeline
consumer at runtime.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.dossier.schema import Dossier

logger = logging.getLogger(__name__)


def serialize_dossier(dossier: Dossier, output_path: str) -> str:
    """Serialize the full Dossier to a JSON file.

    Args:
        dossier: Populated Dossier instance.
        output_path: Absolute path to write _dossier.json.

    Returns:
        The path that was written.
    """
    data = dossier.to_dict()

    # Build tag distribution from responses
    tag_dist: dict[str, int] = {}
    for r in dossier.responses:
        for t in r.tags:
            tag_dist[t] = tag_dist.get(t, 0) + 1

    data["_meta"] = {
        "response_count": len(dossier.responses),
        "unique_tags": sorted(dossier.all_tags()),
        "tag_distribution": tag_dist,
        "agents_completed": list(dossier.agents_completed),
        "agents_failed": list(dossier.agents_failed),
        # Legacy fields (kept during migration)
        "section_keys": list(dossier.sections.keys()),
        "security_finding_count": len(dossier.security),
        "conflict_count": len(dossier.conflicts),
        "emitted_tags": list(dossier.emitted_tags),
        "serialized_at": datetime.now(timezone.utc).isoformat(),
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    logger.info(
        "[Dossier] Serialized to %s  (responses=%d, tags=%s)",
        output_path,
        len(dossier.responses),
        sorted(dossier.all_tags()),
    )
    return output_path


def dossier_output_path(
    repo_path: str,
    repo_name: Optional[str] = None,
    wiki_artifacts_dir: Optional[str] = None,
) -> str:
    """Derive the canonical _dossier.json path.

    Mirrors the safe-name logic in md_exporter so _dossier.json and
    _compressor.md land in the same directory.

    Args:
        repo_path: Absolute local path to the cloned repository (used as
            fallback when repo_name is not provided).
        repo_name: Human-readable repo name, e.g. "openai-agents-python".
            Prefer passing this explicitly — it matches what export_wiki_artifacts
            receives so both files land in the same directory.
        wiki_artifacts_dir: Override the wiki artifacts root. If None, derived
            from settings.repo_cache_dir (same logic as v2_pipeline.py).

    Returns:
        Absolute path to _dossier.json.
    """
    from src.config import get_settings
    settings = get_settings()

    if wiki_artifacts_dir is None:
        wiki_artifacts_dir = str(Path(settings.repo_cache_dir).parent / "wiki_artifacts")

    name = repo_name if repo_name else Path(repo_path).name
    safe_name = re.sub(r"[^\w\-]", "_", name)
    return str(Path(wiki_artifacts_dir) / safe_name / "_dossier.json")
