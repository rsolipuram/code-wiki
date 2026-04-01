"""Reference page builder using canonical structured page builders.

Builds:
  - Getting Started
  - Function Index
  - Glossary
  - API Reference
"""

import logging
import time
from typing import Optional

from src.parsers.base import ParsedEntity
from src.wiki.page_builders.special_pages import (
    build_api_reference,
    build_function_index,
    build_getting_started,
    build_glossary,
)

logger = logging.getLogger(__name__)


def build_reference_pages(
    dossier_dict: dict,  # kept for call-site compatibility
    compressed: dict,  # kept for call-site compatibility
    fingerprint: dict,
    repo_name: str,
    repo_url: str,
    entities: list[ParsedEntity],
    repo_path: str,
    analysis_id: Optional[str] = None,
) -> list[dict]:
    """Build all fixed reference pages as V3Section-compatible dicts."""
    _ = (dossier_dict, compressed)  # intentionally unused
    pages: list[dict] = []

    t0 = time.monotonic()
    try:
        gs_content = build_getting_started(
            repo_name=repo_name,
            repo_path=repo_path,
            fingerprint_dict=fingerprint or {},
            repo_url=repo_url,
            analysis_id=analysis_id,
        )
    except Exception as exc:
        logger.warning("Getting Started generation failed: %s", exc)
        gs_content = {
            "page_type": "getting_started",
            "version": 2,
            "prerequisites": [],
            "setup_steps": [],
            "configuration": [],
            "quick_links": [],
            "_meta": {"fallback_used": True, "error": str(exc)[:200]},
        }
    pages.append(_as_section("getting-started", "Getting Started", gs_content))

    try:
        fi_content = build_function_index(entities, repo_path=repo_path)
    except Exception as exc:
        logger.warning("Function Index generation failed: %s", exc)
        fi_content = {
            "page_type": "function_index",
            "version": 2,
            "total_count": 0,
            "shown_count": 0,
            "grouped": False,
            "index": {},
            "_meta": {"fallback_used": True, "error": str(exc)[:200]},
        }
    pages.append(_as_section("function-index", "Function Index", fi_content))

    try:
        glossary_content = build_glossary(
            entities=entities,
            repo_path=repo_path,
            analysis_id=analysis_id,
        )
    except Exception as exc:
        logger.warning("Glossary generation failed: %s", exc)
        glossary_content = {
            "page_type": "glossary",
            "version": 2,
            "terms": [],
            "total_count": 0,
            "_meta": {"fallback_used": True, "error": str(exc)[:200]},
        }
    pages.append(_as_section("glossary", "Glossary", glossary_content))

    try:
        api_content = build_api_reference(entities=entities, repo_path=repo_path)
    except Exception as exc:
        logger.warning("API Reference generation failed: %s", exc)
        api_content = {
            "page_type": "api_reference",
            "version": 2,
            "total_count": 0,
            "index": {},
            "_meta": {"fallback_used": True, "error": str(exc)[:200]},
        }
    pages.append(_as_section("api-reference", "API Reference", api_content))

    logger.info("Reference pages built: %d pages (%.1fs)", len(pages), time.monotonic() - t0)
    return pages


def _as_section(slug: str, title: str, page_content: dict) -> dict:
    prose_segments = page_content.get("prose_segments", [])
    word_count = page_content.get("word_count")
    if not isinstance(word_count, int):
        word_count = sum(
            len((seg.get("content") or seg.get("text") or "").split())
            for seg in prose_segments
            if seg.get("type") in ("text", "heading")
        )
    return {
        "section_slug": slug,
        "section_title": title,
        "raw_markdown": "",
        "prose_segments": prose_segments,
        "word_count": word_count,
        "critic_passed": True,
        "critic_retries": 0,
        "is_reference_page": True,
        "page_content": page_content,
    }
