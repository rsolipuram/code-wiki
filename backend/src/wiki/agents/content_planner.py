"""Content Planner Agent — V3 wiki pipeline Phase 1.

Single LLM call that reads:
  - Dossier tag summary (all agent findings indexed by tag)
  - Compressor repo_summary + file tree outline
  - File tree structure

Outputs a WikiNav JSON: ordered section list where each section has
title, slug, type, one_liner, focus_tags, seed_files, boundary_hint, cross_refs.

Section count is entirely at the planner's discretion.
"""

import json
import logging
import re
import time
from pathlib import Path

from src.wiki.agents.graph import report_agent_progress
from src.wiki.agents.model import get_wiki_model
from src.wiki.v3_types import SectionSpec, V3WikiState, WikiNav

logger = logging.getLogger(__name__)

PLANNER_SYSTEM = """\
You are a wiki curator organizing pre-analyzed codebase findings into a \
documentation table of contents.

Your job is to GROUP and ORGANIZE the analysis data below — NOT to invent \
topics. Every section you create must be backed by actual dossier findings \
and reference actual files that exist in the repository.

Output ONLY valid JSON with this exact structure:
{
  "title": "Project Name — Documentation",
  "sections": [
    {
      "slug": "url-safe-slug",
      "title": "Clear Section Title",
      "type": "concept|architecture|workflow|reference|home",
      "one_liner": "One sentence describing what this section covers",
      "focus_tags": ["architecture", "dependencies"],
      "seed_files": ["src/relevant/file.py", "another/key/file.ts"],
      "boundary_hint": "Focus on X and Y; skip Z (covered in section 'Other Section')",
      "cross_refs": ["slug-of-related-section"]
    }
  ]
}

Rules:
- First section MUST be type="home" — an overview of the entire project.
- ONLY create sections for topics that have actual dossier findings. \
If a tag has 0 findings, do NOT create a section for it.
- seed_files MUST be copied exactly from the file list provided. \
Do NOT invent or guess file paths. If unsure, leave seed_files empty.
- focus_tags MUST reference real dossier tags from the tag distribution.
- Section count MUST match the project's actual complexity: \
{section_cap}
- boundary_hint prevents agents from writing duplicate content across sections.
- cross_refs should list slugs of related sections.
- Output ONLY the JSON object. No markdown fences, no explanation, no preamble.
"""


def content_planner_node(state: V3WikiState) -> dict:
    """LangGraph node: run Content Planner to produce WikiNav.

    Reads dossier + compressed + all_files from state.
    Returns state update: {"wiki_nav": WikiNav.to_dict()}.
    """
    t0 = time.monotonic()
    report_agent_progress("content_planner", "running", "Planning wiki structure...")

    dossier_dict = state.get("dossier") or {}
    compressed = state.get("compressed") or {}
    all_files = state.get("all_files") or []
    repo_name = state.get("repo_name") or "project"
    repo_path = state.get("repo_path") or ""

    # Build compact prompt context
    context = _build_planner_context(dossier_dict, compressed, all_files, repo_path, repo_name)

    # Derive section cap from repo size
    n_files = len(all_files)
    if n_files < 20:
        section_cap = "max 3 sections (very small project)"
    elif n_files < 50:
        section_cap = "max 5 sections (small project)"
    elif n_files < 200:
        section_cap = "max 8 sections (medium project)"
    else:
        section_cap = "max 12 sections (large project)"

    system_prompt = PLANNER_SYSTEM.replace("{section_cap}", section_cap)

    model = get_wiki_model(temperature=0.3, max_tokens=4096)

    try:
        response = model.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ])
        raw = response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        logger.error("Content planner LLM call failed: %s", exc)
        wiki_nav = _fallback_nav(repo_name)
        report_agent_progress("content_planner", "complete", "Used fallback nav (LLM error)")
        return {
            "wiki_nav": wiki_nav.to_dict(),
            "agent_results": [{"agent": "content_planner", "success": False, "elapsed": time.monotonic() - t0}],
        }

    wiki_nav = _parse_wiki_nav(raw, repo_name)

    # Validate seed_files against actual repo files
    wiki_nav = _validate_nav(wiki_nav, all_files)

    elapsed = time.monotonic() - t0
    logger.info(
        "Content planner complete: %d sections (%.1fs)", len(wiki_nav.sections), elapsed
    )
    report_agent_progress(
        "content_planner", "complete",
        f"{len(wiki_nav.sections)} sections planned",
    )

    return {
        "wiki_nav": wiki_nav.to_dict(),
        "agent_results": [{"agent": "content_planner", "success": True, "elapsed": elapsed}],
    }


# ── Context builders ──────────────────────────────────────────────────────────

def _build_planner_context(
    dossier_dict: dict,
    compressed: dict,
    all_files: list[str],
    repo_path: str,
    repo_name: str,
) -> str:
    parts: list[str] = [f"# Codebase: {repo_name}\n"]

    # Repo-level summary
    repo_summary = compressed.get("repo_summary", "")
    if repo_summary:
        parts.append(f"## Repo Summary\n{repo_summary[:1200]}\n")

    # Call graph summary
    call_graph_summary = compressed.get("call_graph_summary", "")
    if call_graph_summary:
        parts.append(f"## Call Graph Overview\n{call_graph_summary[:600]}\n")

    # Tag distribution (tells planner which dossier tags are populated)
    meta = dossier_dict.get("_meta", {})
    tag_dist = meta.get("tag_distribution", {})
    if tag_dist:
        sorted_tags = sorted(tag_dist.items(), key=lambda x: -x[1])
        tag_summary = ", ".join(f"{t} ({n})" for t, n in sorted_tags[:20])
        parts.append(f"## Available Dossier Tags\n{tag_summary}\n")

    # Key agent findings — expanded budget
    findings = _summarize_responses(dossier_dict, max_per_tag=2, max_chars=3000)
    if findings:
        parts.append(f"## Key Agent Findings\n{findings}\n")

    # Per-file summaries (entities, exports, deps) — from compressed data
    file_summaries = compressed.get("file_summaries", {})
    if file_summaries:
        fs_lines = []
        for fpath, fdata in list(file_summaries.items())[:50]:
            entities = fdata.get("key_entities", [])
            exports = fdata.get("exported_symbols", [])
            lang = fdata.get("language", "")
            summary = fdata.get("summary", "")
            parts_list = [fpath]
            if lang:
                parts_list.append(f"({lang})")
            if summary:
                parts_list.append(f"— {summary[:100]}")
            if entities:
                parts_list.append(f"entities: {', '.join(entities[:5])}")
            if exports:
                parts_list.append(f"exports: {', '.join(exports[:5])}")
            fs_lines.append(" ".join(parts_list))
        if fs_lines:
            parts.append("## File Summaries\n" + "\n".join(fs_lines) + "\n")

    # Key entities — top code symbols
    key_entities = compressed.get("key_entities", [])
    if key_entities:
        # key_entities can be list of strings or list of dicts
        entity_names = []
        for e in key_entities[:40]:
            if isinstance(e, str):
                entity_names.append(e)
            elif isinstance(e, dict):
                entity_names.append(e.get("name", str(e)))
        if entity_names:
            parts.append(f"## Key Code Entities\n{', '.join(entity_names)}\n")

    # Full file list — the ONLY valid paths for seed_files
    parts.append(
        "## Complete File List (ONLY use these exact paths for seed_files)\n"
        + "\n".join(all_files)
        + "\n"
    )

    # Directory summaries
    dir_summaries = compressed.get("directory_summaries", {})
    if dir_summaries:
        dir_lines = []
        for dir_path, summary in list(dir_summaries.items())[:15]:
            s = summary.get("summary", "") if isinstance(summary, dict) else ""
            if s:
                dir_lines.append(f"- {dir_path}: {s[:120]}")
        if dir_lines:
            parts.append("## Directory Context\n" + "\n".join(dir_lines) + "\n")

    return "\n".join(parts)


def _summarize_responses(dossier_dict: dict, max_per_tag: int = 1, max_chars: int = 1200) -> str:
    """Compact summary of dossier responses for planner context."""
    by_tag: dict[str, list] = {}
    for resp in dossier_dict.get("responses", []):
        for tag in resp.get("tags", []):
            by_tag.setdefault(tag, []).append(resp)

    priority_tags = ["architecture", "patterns", "data-flow", "api-surface", "dependencies"]
    other_tags = [t for t in by_tag if t not in priority_tags]
    ordered_tags = priority_tags + other_tags

    lines: list[str] = []
    total_chars = 0

    for tag in ordered_tags:
        if tag not in by_tag:
            continue
        for resp in by_tag[tag][:max_per_tag]:
            output = resp.get("output", {})
            summary = output.get("summary", "") or _first_dict_value(output, 300)
            if summary:
                line = f"[{tag}] {summary[:200]}"
                lines.append(line)
                total_chars += len(line)
                if total_chars >= max_chars:
                    return "\n".join(lines)

    return "\n".join(lines)


def _build_file_tree(all_files: list[str], repo_path: str, max_entries: int = 60) -> str:
    """Build a depth-limited directory tree from file list."""
    # Collect unique directory paths
    dirs: set[str] = set()
    for f in all_files:
        parts = Path(f).parts
        for i in range(1, min(len(parts), 4)):  # max depth 3
            dirs.add("/".join(parts[:i]))

    entries: list[str] = []
    seen_dirs: set[str] = set()

    for dir_path in sorted(dirs):
        depth = dir_path.count("/")
        indent = "  " * depth
        name = dir_path.split("/")[-1]
        entries.append(f"{indent}{name}/")
        seen_dirs.add(dir_path)
        if len(entries) >= max_entries:
            break

    # Add a sample of files
    file_count = 0
    for f in sorted(all_files):
        parent = str(Path(f).parent)
        depth = parent.count("/") + 1 if parent != "." else 0
        indent = "  " * depth
        name = Path(f).name
        entries.append(f"{indent}{name}")
        file_count += 1
        if file_count >= 30 or len(entries) >= max_entries:
            break

    return "\n".join(entries[:max_entries])


def _first_dict_value(d: dict, max_chars: int) -> str:
    for v in d.values():
        if isinstance(v, str) and v.strip():
            return v[:max_chars]
        if isinstance(v, list) and v:
            return str(v[0])[:max_chars]
    return ""


# ── Post-LLM validation ───────────────────────────────────────────────────────

def _validate_nav(nav: WikiNav, all_files: list[str]) -> WikiNav:
    """Validate and correct seed_files against real file list.

    - Exact match → keep
    - Fuzzy match (same filename, wrong dir) → correct to real path
    - No match → drop
    - Drop sections that have 0 valid seed_files AND 0 valid focus_tags
      (unless it's the home section).
    """
    # Build lookup: filename → list of full paths
    filename_to_paths: dict[str, list[str]] = {}
    all_files_set = set(all_files)
    for fp in all_files:
        name = Path(fp).name
        filename_to_paths.setdefault(name, []).append(fp)

    valid_sections = []
    for section in nav.sections:
        validated_files = []
        for seed in (section.seed_files or []):
            if seed in all_files_set:
                validated_files.append(seed)
            else:
                # Fuzzy: try matching just the filename
                basename = Path(seed).name
                matches = filename_to_paths.get(basename, [])
                if len(matches) == 1:
                    logger.info("seed_files fuzzy match: %r → %r", seed, matches[0])
                    validated_files.append(matches[0])
                elif matches:
                    # Multiple matches — pick the shortest path (most likely correct)
                    best = min(matches, key=len)
                    logger.info("seed_files fuzzy match (ambiguous): %r → %r", seed, best)
                    validated_files.append(best)
                else:
                    logger.warning("seed_files dropped (not found): %r", seed)

        section.seed_files = validated_files

        # Keep home sections unconditionally
        if section.type == "home":
            valid_sections.append(section)
            continue

        # Drop sections with no grounding at all
        if not section.seed_files and not section.focus_tags:
            logger.warning(
                "Dropping section %r — no valid seed_files or focus_tags", section.slug
            )
            continue

        valid_sections.append(section)

    nav.sections = valid_sections
    return nav


# ── Response parsing ──────────────────────────────────────────────────────────

def _parse_wiki_nav(raw: str, repo_name: str) -> WikiNav:
    """Parse LLM response into WikiNav, with robust fallback."""
    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()

    # Try to extract JSON object
    m = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if m:
        cleaned = m.group(0)

    try:
        data = json.loads(cleaned)
        nav = WikiNav.from_dict(data)
        if not nav.sections:
            raise ValueError("No sections in parsed nav")
        # Validate slugs
        _normalize_slugs(nav)
        return nav
    except Exception as exc:
        logger.warning("Failed to parse WikiNav JSON: %s\nRaw: %s", exc, raw[:500])
        return _fallback_nav(repo_name)


def _normalize_slugs(nav: WikiNav) -> None:
    """Ensure all slugs are URL-safe and unique."""
    seen: set[str] = set()
    for section in nav.sections:
        if not section.slug:
            section.slug = _title_to_slug(section.title)
        # Make URL-safe
        section.slug = re.sub(r"[^a-z0-9-]", "-", section.slug.lower())
        section.slug = re.sub(r"-+", "-", section.slug).strip("-")
        # Deduplicate
        base = section.slug
        counter = 2
        while section.slug in seen:
            section.slug = f"{base}-{counter}"
            counter += 1
        seen.add(section.slug)


def _title_to_slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _fallback_nav(repo_name: str) -> WikiNav:
    """Minimal fallback if planner LLM fails."""
    return WikiNav(
        title=f"{repo_name} — Documentation",
        sections=[
            SectionSpec(
                slug="overview",
                title="Overview",
                type="home",
                one_liner=f"Overview of the {repo_name} codebase",
                focus_tags=["architecture"],
                seed_files=[],
            ),
            SectionSpec(
                slug="architecture",
                title="Architecture",
                type="architecture",
                one_liner="System architecture and design patterns",
                focus_tags=["architecture", "patterns"],
                seed_files=[],
            ),
        ],
    )
