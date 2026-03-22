"""CRITIC agent — deterministic quality gate for the writer output.

Checks that each wiki section's prose mentions all entities listed in the
planner's `required_entities` field. No LLM calls — pure string matching.

Returns a `critic_result` dict that the conditional edge in graph.py uses to
decide whether to retry the writer or proceed to annotator/diagrammer/tabulator.
"""

import logging
import re
import time

from src.wiki.agents.graph import report_agent_progress
from src.wiki.agents.state import WikiState

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


def critic_node(state: WikiState) -> dict:
    """CRITIC node — verify writer prose covers all required entities.

    Deterministic: no LLM calls. Uses case-insensitive substring matching
    to check that each name in `required_entities` appears in the prose.

    Returns state update with `critic_result` dict.
    """
    t0 = time.monotonic()
    logger.info("CRITIC agent starting")
    report_agent_progress("critic", "running", "Auditing writer output for entity coverage")

    plan = state.get("plan") or {}
    narrated_sections = state.get("narrated_sections") or {}
    retry_count = state.get("writer_retry_count") or 0

    sections = plan.get("sections") or []
    missing_per_section: dict[str, list[str]] = {}
    total_required = 0
    total_missing = 0

    for section in sections:
        section_id = section.get("id", "")
        if not section_id:
            continue

        required = _collect_required_entities(section)
        if not required:
            continue
        total_required += len(required)

        # Get the prose for this section from narrated_sections
        narrated = narrated_sections.get(section_id) or {}
        prose = narrated.get("prose") or ""

        # Also check system_narrative for home-page-like content
        if not prose and section_id in ("home", "overview", "introduction"):
            prose = state.get("system_narrative") or ""

        missing = _find_missing_entities(required, prose)
        if missing:
            missing_per_section[section_id] = missing
            total_missing += len(missing)

    passed = len(missing_per_section) == 0
    coverage_pct = (
        (total_required - total_missing) / total_required * 100
        if total_required > 0 else 100.0
    )

    if passed:
        logger.info(
            "CRITIC: PASSED — all %d required entities mentioned (%.1fs)",
            total_required, time.monotonic() - t0,
        )
        report_agent_progress("critic", "complete", f"Passed — {total_required} entities covered")
    else:
        missing_count = sum(len(v) for v in missing_per_section.values())
        logger.warning(
            "CRITIC: FAILED — %d entities missing across %d sections (retry %d/%d, %.1fs)",
            missing_count, len(missing_per_section), retry_count, MAX_RETRIES,
            time.monotonic() - t0,
        )
        report_agent_progress(
            "critic", "complete",
            f"Failed — {missing_count} missing entities, retry {retry_count}/{MAX_RETRIES}",
        )

    critic_result = {
        "passed": passed,
        "missing_per_section": missing_per_section,
        "retry_count": retry_count,
        "coverage_pct": round(coverage_pct, 1),
        "total_required": total_required,
        "total_missing": total_missing,
    }

    return {
        "critic_result": critic_result,
        "agent_results": [{
            "agent": "critic",
            "success": True,
            "passed": passed,
            "coverage_pct": round(coverage_pct, 1),
            "retry_count": retry_count,
            "elapsed": time.monotonic() - t0,
        }],
    }


def critic_route(state: WikiState) -> str:
    """Conditional routing function: retry writer or proceed to enrichment.

    Returns "writer" if critic failed and retries remain, otherwise "annotator".
    LangGraph will fan out to annotator/diagrammer/tabulator from "annotator" node.
    """
    critic_result = state.get("critic_result") or {}
    passed = critic_result.get("passed", True)
    retry_count = state.get("writer_retry_count") or 0

    if not passed and retry_count < MAX_RETRIES:
        logger.info("CRITIC routing: → writer (retry %d)", retry_count + 1)
        return "writer"

    if not passed:
        logger.warning(
            "CRITIC routing: → annotator (max retries %d exhausted, proceeding with warnings)",
            MAX_RETRIES,
        )
    return "annotator"


def _collect_required_entities(section: dict) -> list[str]:
    """Collect all required_entities from a section and its subsections."""
    required: list[str] = list(section.get("required_entities") or [])
    for sub in section.get("subsections") or []:
        required.extend(sub.get("required_entities") or [])
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for name in required:
        if name and name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


def _find_missing_entities(required: list[str], prose: str) -> list[str]:
    """Return entities from `required` not found in `prose`.

    Matching is case-insensitive word-boundary check so "triage_agent" matches
    "triage_agent" or "TRIAGE_AGENT" but not "triage_agent_config".
    """
    if not prose:
        return list(required)

    prose_lower = prose.lower()
    missing: list[str] = []
    for name in required:
        if not name:
            continue
        # Build a pattern: exact name OR name with underscores replaced by spaces
        name_lower = name.lower()
        name_spaced = name_lower.replace("_", " ")
        # Check both the raw name and the space-separated version
        found = name_lower in prose_lower or (name_spaced != name_lower and name_spaced in prose_lower)
        if not found:
            # Try word-boundary match for camelCase/PascalCase names
            try:
                pattern = re.compile(r'\b' + re.escape(name_lower) + r'\b', re.IGNORECASE)
                found = bool(pattern.search(prose))
            except re.error:
                found = False
        if not found:
            missing.append(name)
    return missing
