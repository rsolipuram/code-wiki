"""PerformanceHotspotScanner — identifies N+1 queries, blocking I/O, missing caching (1 LLM call)."""

import json
import logging

from src.agents.primitives.tools import search_code
from src.dossier.manager import DossierManager
from src.llm.client import chat

logger = logging.getLogger(__name__)

AGENT_NAME = "performance_hotspot_scanner"


def run(repo_path: str, dossier_manager: DossierManager) -> None:
    # Heuristic pre-filtering
    n_plus_one = search_code(repo_path, r"for\s+\w+\s+in\s+\w+.*\.(filter|get|find|query)\(",
                             extensions=[".py", ".ts", ".js"])
    blocking_io = search_code(repo_path, r"open\(|readFile\b|time\.sleep|Thread\.sleep",
                              extensions=[".py", ".ts", ".js", ".java"])
    no_cache = search_code(repo_path, r"def\s+get_|async\s+function\s+fetch",
                           extensions=[".py", ".ts", ".js"])

    context = (
        f"Potential N+1 query patterns: {len(n_plus_one)}\n"
        f"Blocking I/O patterns: {len(blocking_io)}\n"
        f"Uncached fetch functions: {len(no_cache)}\n"
        f"Sample N+1: {n_plus_one[0] if n_plus_one else 'none'}"
    )

    prompt = f"""Identify performance hotspots from this heuristic scan:

{context}

Return JSON only:
{{
  "hotspots": [
    {{"type": "<n+1|blocking-io|memory-leak|missing-cache>", "file": "<path>", "description": "<desc>"}},
    ...
  ],
  "severity_assessment": "<high|medium|low>"
}}"""

    try:
        response = chat(messages=[{"role": "user", "content": prompt}])
        data = json.loads(response)
        hotspots = data.get("hotspots", [])
    except Exception as exc:
        logger.warning("PerformanceHotspotScanner failed: %s", exc)
        hotspots = []

    extra = dossier_manager.get_section("extra") or {}
    dossier_manager.write_section("extra", {**extra, "performance_hotspots": hotspots})
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("PerformanceHotspotScanner: %d hotspots", len(hotspots))
