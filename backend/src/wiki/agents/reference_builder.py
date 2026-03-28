"""Reference Page Builder — generates fixed wiki pages outside planner scope.

Builds:
  - Getting Started   (setup, prerequisites, first-run)
  - Glossary          (key terms from dossier)
  - API Reference     (public API surface from dossier + entities)

These pages are always generated and appended after concept sections.
"""

import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


def build_reference_pages(
    dossier_dict: dict,
    compressed: dict,
    fingerprint: dict,
    repo_name: str,
    repo_url: str,
    llm_fn: Any,  # callable(system, user) → str
) -> list[dict]:
    """Build all fixed reference page V3Sections.

    Returns list of V3Section-compatible dicts.
    """
    pages = []

    t0 = time.monotonic()
    try:
        pages.append(_build_getting_started(dossier_dict, compressed, fingerprint, repo_name, repo_url, llm_fn))
    except Exception as exc:
        logger.warning("Getting Started generation failed: %s", exc)
        pages.append(_fallback_page("getting-started", "Getting Started", f"Setup guide for {repo_name}."))

    try:
        pages.append(_build_glossary(dossier_dict, compressed, repo_name, llm_fn))
    except Exception as exc:
        logger.warning("Glossary generation failed: %s", exc)
        pages.append(_fallback_page("glossary", "Glossary", "Key terms and concepts."))

    try:
        pages.append(_build_api_reference(dossier_dict, compressed, repo_name, llm_fn))
    except Exception as exc:
        logger.warning("API Reference generation failed: %s", exc)
        pages.append(_fallback_page("api-reference", "API Reference", "Public API surface."))

    logger.info("Reference pages built: %d pages (%.1fs)", len(pages), time.monotonic() - t0)
    return pages


# ── Individual page builders ──────────────────────────────────────────────────

def _build_getting_started(
    dossier_dict: dict,
    compressed: dict,
    fingerprint: dict,
    repo_name: str,
    repo_url: str,
    llm_fn: Any,
) -> dict:
    context = _build_context_summary(dossier_dict, compressed, max_responses=8)
    langs = fingerprint.get("languages", [])
    runtime_info = json.dumps({"languages": langs, "repo_url": repo_url}, indent=2)

    system = (
        "You are a technical writer creating a Getting Started guide for developers. "
        "Write clear, actionable setup steps. Use numbered lists for steps. "
        "Include: prerequisites, installation, configuration, and first-run instructions. "
        "Use <callout type='tip'> for helpful hints and <callout type='warning'> for gotchas. "
        "Return markdown only."
    )
    user = (
        f"# Getting Started with {repo_name}\n\n"
        f"Repository: {repo_url}\n\n"
        f"Runtime info:\n{runtime_info}\n\n"
        f"Codebase context:\n{context}"
    )

    raw = llm_fn(system, user)
    return _make_section("getting-started", "Getting Started", raw)


def _build_glossary(
    dossier_dict: dict,
    compressed: dict,
    repo_name: str,
    llm_fn: Any,
) -> dict:
    # Pull architecture + patterns responses for terminology
    arch_responses = _get_tag_responses(dossier_dict, "architecture", max=3)
    pat_responses = _get_tag_responses(dossier_dict, "patterns", max=3)
    key_entities = compressed.get("key_entities", [])[:20]

    context_parts = []
    for resp in arch_responses + pat_responses:
        context_parts.append(json.dumps(resp.get("output", {}), indent=2))
    if key_entities:
        context_parts.append(f"Key entities: {json.dumps([e.get('name') for e in key_entities])}")

    system = (
        "You are a technical writer creating a project glossary. "
        "Define key terms, concepts, patterns, and domain-specific language used in this codebase. "
        "Format each entry as: **Term**: definition. "
        "Group related terms under headings (## Category). "
        "Return markdown only."
    )
    user = f"# Glossary for {repo_name}\n\n" + "\n\n".join(context_parts)

    raw = llm_fn(system, user)
    return _make_section("glossary", "Glossary", raw)


def _build_api_reference(
    dossier_dict: dict,
    compressed: dict,
    repo_name: str,
    llm_fn: Any,
) -> dict:
    api_responses = _get_tag_responses(dossier_dict, "api-surface", max=4)
    key_entities = compressed.get("key_entities", [])[:30]

    api_context = []
    for resp in api_responses:
        api_context.append(json.dumps(resp.get("output", {}), indent=2))

    entity_list = "\n".join(
        f"- {e.get('name', '')} ({e.get('entity_type', '')}) in {e.get('file_path', '')}"
        for e in key_entities
        if e.get("entity_type") in ("function", "class", "method")
    )

    system = (
        "You are a technical writer creating an API reference. "
        "Document public functions, classes, and endpoints. "
        "For each: name, signature/parameters, return value, description. "
        "Use ## headings for sections, ### for each entry. "
        "Return markdown only."
    )
    user = (
        f"# API Reference for {repo_name}\n\n"
        f"API surface analysis:\n" + "\n".join(api_context) + "\n\n"
        f"Key entities:\n{entity_list}"
    )

    raw = llm_fn(system, user)
    return _make_section("api-reference", "API Reference", raw)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_context_summary(dossier_dict: dict, compressed: dict, max_responses: int = 6) -> str:
    """Build a compact context string from dossier + compressor for prompts."""
    parts = []

    repo_summary = compressed.get("repo_summary", "")
    if repo_summary:
        parts.append(f"Repo summary: {repo_summary[:500]}")

    for resp in dossier_dict.get("responses", [])[:max_responses]:
        output = resp.get("output", {})
        summary = output.get("summary", "") or str(output)[:200]
        parts.append(f"[{resp.get('agent_name', '?')}]: {summary}")

    return "\n".join(parts)


def _get_tag_responses(dossier_dict: dict, tag: str, max: int = 5) -> list[dict]:
    return [
        r for r in dossier_dict.get("responses", [])
        if tag in r.get("tags", [])
    ][:max]


def _make_section(slug: str, title: str, raw_markdown: str) -> dict:
    from src.wiki.agents.tag_assembler import assemble
    prose_segments = assemble(raw_markdown)
    word_count = sum(
        len((seg.get("content") or seg.get("text") or "").split())
        for seg in prose_segments
        if seg.get("type") in ("text", "heading")
    )
    return {
        "section_slug": slug,
        "section_title": title,
        "raw_markdown": raw_markdown,
        "prose_segments": prose_segments,
        "word_count": word_count,
        "critic_passed": True,
        "critic_retries": 0,
        "is_reference_page": True,
    }


def _fallback_page(slug: str, title: str, description: str) -> dict:
    return {
        "section_slug": slug,
        "section_title": title,
        "raw_markdown": description,
        "prose_segments": [{"type": "text", "content": description}],
        "word_count": len(description.split()),
        "critic_passed": False,
        "critic_retries": 0,
        "is_reference_page": True,
    }
