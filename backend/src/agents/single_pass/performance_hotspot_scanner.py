"""PerformanceHotspotScanner — identifies N+1 queries, blocking I/O, missing caching (1 LLM call)."""

import json
import logging

from src.agents.primitives.tools import search_code
from src.dossier.manager import DossierManager
from src.dossier.schema import AgentResponse, PerformanceHotspot, PerformanceProfile
from src.llm.client import chat

logger = logging.getLogger(__name__)

AGENT_NAME = "performance_hotspot_scanner"
TAGS = ["performance", "optimization"]


def run(repo_path: str, dossier_manager: DossierManager, compressed=None) -> None:
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
    {{"type": "<n+1|blocking-io|memory-leak|missing-cache>", "file": "<path>", "line": <int>, "description": "<desc>"}},
    ...
  ],
  "severity_assessment": "<high|medium|low>"
}}"""

    hotspots: list[PerformanceHotspot] = []
    n_plus_one_detected = False
    blocking_io_files: list[str] = []

    try:
        response = chat(messages=[{"role": "user", "content": prompt}])
        data = json.loads(response)
        for h in data.get("hotspots", []):
            issue_type = h.get("type", "unknown")
            file_path = h.get("file", "")
            line_number = int(h.get("line", 0))
            description = h.get("description", "")
            hotspots.append(PerformanceHotspot(
                file_path=file_path,
                line_number=line_number,
                issue_type=issue_type,
                description=description,
            ))
            if "n+1" in issue_type.lower() or "n_plus_one" in issue_type.lower():
                n_plus_one_detected = True
            if "blocking" in issue_type.lower() and file_path:
                blocking_io_files.append(file_path)
    except Exception as exc:
        logger.warning("PerformanceHotspotScanner failed: %s", exc)

    perf_profile = PerformanceProfile(
        agent_name=AGENT_NAME,
        hotspots=hotspots,
        n_plus_one_detected=n_plus_one_detected,
        blocking_io_files=list(set(blocking_io_files)),
    )
    dossier_manager.write_response(AgentResponse(
        agent_name=AGENT_NAME,
        tags=TAGS,
        confidence=perf_profile.confidence,
        output=perf_profile.model_dump(),
        output_type="PerformanceProfile",
    ))
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("PerformanceHotspotScanner: %d hotspots", len(hotspots))
