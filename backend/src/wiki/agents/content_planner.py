"""Content Planner Agent — V3 wiki pipeline Phase 1.

Single LLM call that reads:
  - Dossier tag summary (all agent findings indexed by tag)
  - Compressor repo_summary + file tree outline
  - File tree structure

Outputs a WikiNav JSON: ordered section list where each section has
title, slug, type, one_liner, focus_tags, seed_files, boundary_hint, cross_refs.

Section count is entirely at the planner's discretion — no artificial caps.
"""

import json
import os
import logging
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.wiki.agents.graph import report_agent_progress
from src.wiki.agents.model import get_wiki_model
from src.wiki.pipeline_types import MenuGroupPlan, SectionSpec, V3WikiState, WikiNav

logger = logging.getLogger(__name__)

PLANNER_SYSTEM = """\
You are a NAVIGATION SPECIALIST designing the sidebar table-of-contents for \
a code documentation wiki. Think like a senior technical writer organizing \
a developer portal — the navigation should be intuitive, hierarchical, and \
complete.

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
      "cross_refs": ["slug-of-related-section"],
      "menu_group": "Architecture",
      "menu_label": "System Overview",
      "key_insights": [
        "All incoming requests are routed through the triage agent before reaching specialists",
        "Context is rebuilt from the memory store on every conversation turn"
      ]
    }
  ]
}

TAXONOMY DESIGN PRINCIPLES:
- Design the navigation like a well-organized documentation sidebar. \
A reader should be able to scan the menu groups and immediately understand \
the project's architecture and find what they need.
- Create as many sections as the content genuinely warrants. Do NOT \
artificially limit or pad — let the project's actual complexity drive the \
structure. A 10-file utility might need 3 sections; a 200-file framework \
might need 15+.
- {section_cap}

MENU HIERARCHY RULES:
- First section MUST be type="home" with NO menu_group (it stands alone at the top).
- ALL other sections MUST have a menu_group and menu_label.
- menu_group is the parent heading (e.g. "Architecture", "Backend", "Frontend", \
"Data Layer", "DevOps", "API"). Each group represents a distinct architectural \
concern or domain area.
- menu_label is the SHORT child label shown under the group. Do NOT repeat the \
group name in menu_label (e.g. group="API" → label="Endpoints", not "API Endpoints").
- Aim for 3-5 sections per group. If a group would need more, make the extra \
topics subsections within a broader page rather than separate pages. For example, \
instead of separate pages for "UI Layout", "UI Components", "UI Subcomponents", \
and "UI Primitives", create one "UI Components" page that covers all of them.
- Every group SHOULD have 2+ sections. If a topic stands alone, merge it into \
the closest related group rather than creating a single-item group.
- Groups should be ordered by importance: Architecture/Core first, then \
major subsystems, then supporting concerns (config, DevOps, etc.).

CONSOLIDATION RULES:
- Merge sections that cover the same subsystem or concern. Do NOT create \
separate sections for "UI Structure", "UI Layout", "UI Components" — combine \
into 1-2 sections under a "Frontend" group.
- Implementation details (CORS config, streaming setup, individual utility \
files) belong inside broader sections, NOT as standalone sections.
- BUT do NOT over-consolidate: distinct architectural layers (e.g. agent \
orchestration vs. API endpoints vs. frontend components) deserve their own \
sections even if the project is small.

EXAMPLES — study these carefully:

❌ BAD navigation (too granular, singleton groups, flat):
  menu_group="Architecture", menu_label="Agent Architecture"
  menu_group="API", menu_label="API Layer"
  menu_group="Frontend", menu_label="UI Architecture"
  menu_group="Frontend", menu_label="Core UI Components"
  menu_group="Frontend", menu_label="Agent Interface"
  menu_group="Configuration", menu_label="Build & Config"
Problems: Architecture, API, and Configuration are singleton groups (1 item each). \
That produces a sidebar with 4 headings where 3 headings expand to show just 1 link — \
poor UX. Frontend is the only real group.

✅ GOOD navigation (same content, properly grouped):
  menu_group="Architecture", menu_label="System Design"
  menu_group="Architecture", menu_label="Agent Pipeline"
  menu_group="Backend", menu_label="API Layer"
  menu_group="Backend", menu_label="Configuration"
  menu_group="Frontend", menu_label="UI Architecture"
  menu_group="Frontend", menu_label="Components"
  menu_group="Frontend", menu_label="Agent Interface"
Why this works: No singleton groups. Architecture has 2 items (design + agents). \
Backend has 2 items (API + config — both are server-side concerns). \
Frontend has 3 items. Every group expands to reveal 2+ links.

❌ BAD navigation (one-section-per-file anti-pattern):
  menu_group="Core", menu_label="Main Entry"
  menu_group="Core", menu_label="App Config"
  menu_group="Core", menu_label="Constants"
  menu_group="Core", menu_label="Utils"
  menu_group="Core", menu_label="Types"
  menu_group="Routing", menu_label="Router Setup"
  menu_group="Routing", menu_label="Route Handlers"
  menu_group="Routing", menu_label="Middleware"
  menu_group="Data", menu_label="Database Client"
  menu_group="Data", menu_label="Migrations"
  menu_group="Data", menu_label="Models"
  menu_group="Data", menu_label="Queries"
Problems: 12 sections for what is probably 3-4 concerns. Constants, Utils, Types \
are not worth standalone sections — fold them into broader pages.

✅ GOOD navigation (same project, consolidated):
  menu_group="Architecture", menu_label="System Overview"
  menu_group="Architecture", menu_label="Core Modules"
  menu_group="Backend", menu_label="API & Routing"
  menu_group="Backend", menu_label="Middleware"
  menu_group="Data Layer", menu_label="Models & Schema"
  menu_group="Data Layer", menu_label="Queries & Migrations"
Why this works: 6 sections in 3 groups. Each group has 2 items. \
Utils/Types/Constants are covered inside "Core Modules". \
Router + Handlers combined into "API & Routing". \
Database + Models + Queries consolidated into 2 data pages.

KEY TAKEAWAY: Every menu_group in your output MUST contain 2 or more sections. \
If you find yourself creating a group with only 1 section, merge that section \
into the closest related group instead.

CONTENT RULES:
- ONLY create sections for topics that have actual dossier findings. \
If a tag has 0 findings, do NOT create a section for it.
- seed_files MUST be copied exactly from the file list provided. \
Do NOT invent or guess file paths. If unsure, leave seed_files empty.
- focus_tags MUST reference real dossier tags from the tag distribution.
- boundary_hint prevents agents from writing duplicate content across sections.
- cross_refs should list slugs of related sections.
- key_insights is a list of 2-5 critical observations that a wiki writer MUST \
cover in this section. Think: "What would a senior engineer highlight in a \
design review?" Focus on logic flow, entry points, routing patterns, state \
management, error handling strategies, and non-obvious architectural decisions. \
These should be specific and concrete — not generic descriptions. \
Example: "All API requests funnel through triage_agent which classifies intent \
before dispatching to flight_change or booking specialists" is great. \
"This section covers the agent architecture" is useless.
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

    model = get_wiki_model(temperature=0.3)
    log_planner_io = os.environ.get("WIKI_LOG_PLANNER_IO", "").strip().lower() in {
        "1", "true", "yes", "on",
    }

    use_two_phase = len(all_files) >= 200
    try:
        if use_two_phase:
            wiki_nav = _two_phase_plan(
                model=model,
                dossier_dict=dossier_dict,
                compressed=compressed,
                all_files=all_files,
                repo_path=repo_path,
                repo_name=repo_name,
                log_planner_io=log_planner_io,
            )
        else:
            wiki_nav = _single_phase_plan(
                model=model,
                dossier_dict=dossier_dict,
                compressed=compressed,
                all_files=all_files,
                repo_path=repo_path,
                repo_name=repo_name,
                log_planner_io=log_planner_io,
            )
    except Exception as exc:
        logger.error("Content planner LLM call failed: %s", exc)
        wiki_nav = _fallback_nav(repo_name)
        report_agent_progress("content_planner", "complete", "Used fallback nav (LLM error)")
        return {
            "wiki_nav": wiki_nav.to_dict(),
            "agent_results": [{"agent": "content_planner", "success": False, "elapsed": time.monotonic() - t0}],
        }

    # Validate seed_files against actual repo files
    wiki_nav = _validate_nav(wiki_nav, all_files)

    # Ensure every non-home section has menu_group (assign from title if missing)
    _ensure_menu_groups(wiki_nav)

    # Consolidate sections that share the same (menu_group, menu_label) —
    # the LLM often produces multiple sections for the same nav slot.
    _consolidate_sections(wiki_nav)

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


# ── Planner execution modes ────────────────────────────────────────────────────

GROUP_PLANNER_SYSTEM = """\
You are planning wiki sections for ONE sidebar menu group.

Return ONLY valid JSON:
{{
  "sections": [
    {{
      "slug": "url-safe-slug",
      "title": "Section Title",
      "type": "concept|architecture|workflow|reference",
      "one_liner": "One sentence",
      "focus_tags": ["architecture"],
      "seed_files": ["path/file.py"],
      "boundary_hint": "Scope guardrails",
      "cross_refs": ["other-slug"],
      "menu_group": "{group_name}",
      "menu_label": "Short label",
      "key_insights": ["Insight 1", "Insight 2"]
    }}
  ]
}}

Rules:
- Plan ONLY for menu_group "{group_name}".
- Target around {expected_sections} sections (±1 is okay).
- Use only file paths from the provided file list.
- Do not emit a home section.
- Keep section boundaries distinct and non-overlapping.
- Apply this boundary focus: {boundary_hint}
"""


def _single_phase_plan(
    model,
    dossier_dict: dict,
    compressed: dict,
    all_files: list[str],
    repo_path: str,
    repo_name: str,
    log_planner_io: bool,
) -> WikiNav:
    context = _build_planner_context(dossier_dict, compressed, all_files, repo_path, repo_name)
    nav_plan = compressed.get("nav_plan", {})
    n_files = len(all_files)
    if nav_plan and nav_plan.get("sections"):
        nav_count = len(nav_plan["sections"])
        section_cap = (
            f"The nav skeleton below has {nav_count} raw sections derived from "
            f"repository analysis ({n_files} files). Use it as your starting taxonomy. "
            f"Consolidate sections that cover the same subsystem, split sections that "
            f"span unrelated concerns, and group everything into a clear menu hierarchy. "
            f"The skeleton is INPUT — refine it into a professional documentation sidebar."
        )
    else:
        section_cap = (
            f"This project has {n_files} files. Create as many sections as the "
            f"content warrants — enough to cover each distinct concern without overlap."
        )

    system_prompt = PLANNER_SYSTEM.replace("{section_cap}", section_cap)
    if log_planner_io:
        logger.info("PLANNER_LLM_INPUT_SYSTEM:\n%s", system_prompt)
        logger.info("PLANNER_LLM_INPUT_USER:\n%s", context)

    response = model.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context},
    ])
    raw = response.content if hasattr(response, "content") else str(response)
    if log_planner_io:
        logger.info("PLANNER_LLM_RAW_RESPONSE:\n%s", raw)
    return _parse_wiki_nav(raw, repo_name)


def _two_phase_plan(
    model,
    dossier_dict: dict,
    compressed: dict,
    all_files: list[str],
    repo_path: str,
    repo_name: str,
    log_planner_io: bool,
) -> WikiNav:
    groups = _structural_plan(
        model=model,
        compressed=compressed,
        all_files=all_files,
        repo_name=repo_name,
        log_planner_io=log_planner_io,
    )
    if not groups:
        return _single_phase_plan(
            model, dossier_dict, compressed, all_files, repo_path, repo_name, log_planner_io
        )

    workers = min(3, max(1, len(groups)))
    grouped_sections: list[SectionSpec] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _group_section_plan,
                model,
                group,
                dossier_dict,
                compressed,
                all_files,
                repo_path,
                repo_name,
                log_planner_io,
            ): group.group_name
            for group in groups
        }
        for future in as_completed(futures):
            group_name = futures[future]
            try:
                grouped_sections.extend(future.result())
            except Exception as exc:
                logger.warning("Group planner failed for %s: %s", group_name, exc)

    merged_sections = _merge_group_sections(grouped_sections)
    if not merged_sections:
        return _single_phase_plan(
            model, dossier_dict, compressed, all_files, repo_path, repo_name, log_planner_io
        )

    home = _home_section(repo_name, compressed)
    nav = WikiNav(
        title=f"{repo_name} — Documentation",
        sections=[home] + merged_sections,
    )
    _normalize_slugs(nav)
    return nav


def _structural_plan(
    model,
    compressed: dict,
    all_files: list[str],
    repo_name: str,
    log_planner_io: bool,
) -> list[MenuGroupPlan]:
    stats = _top_level_stats(compressed, all_files)
    if not stats:
        return []

    top_dirs = [s["top_dir"] for s in stats]
    stats_lines = []
    for s in stats[:30]:
        top = s["top_dir"]
        cnt = s["file_count"]
        langs = ", ".join(s["languages"][:3]) if s["languages"] else "mixed"
        hint = s["summary"][:180] if s["summary"] else ""
        stats_lines.append(f"- {top}: {cnt} files; langs={langs}; hint={hint}")

    prompt = (
        f"Repository: {repo_name}\n"
        "Top-level directory stats:\n"
        + "\n".join(stats_lines)
        + "\n\nReturn ONLY JSON:\n"
        + '{"groups":[{"group_name":"Core Backend","scope_dirs":["backend","src"],'
        + '"expected_sections":3,"boundary_hint":"what this group should cover",'
        + '"importance":"core|supporting|peripheral"}]}'
        + "\nRules:\n"
        + "- Cover every top-level directory at least once.\n"
        + "- Create 4-10 groups total.\n"
        + "- Keep group names concise and architectural.\n"
    )
    if log_planner_io:
        logger.info("PLANNER_PHASE_A_INPUT:\n%s", prompt)

    groups = []
    try:
        response = model.invoke([
            {"role": "system", "content": "Design high-level wiki menu groups from directory structure."},
            {"role": "user", "content": prompt},
        ])
        raw = response.content if hasattr(response, "content") else str(response)
        if log_planner_io:
            logger.info("PLANNER_PHASE_A_RAW:\n%s", raw)
        parsed = _extract_json_dict(raw)
        groups = _parse_group_plans(parsed, top_dirs)
    except Exception as exc:
        logger.warning("Phase-A structural planner failed: %s", exc)

    if not groups:
        groups = _structural_groups_fallback(stats)
    return _ensure_group_coverage(groups, top_dirs)


def _group_section_plan(
    model,
    group: MenuGroupPlan,
    dossier_dict: dict,
    compressed: dict,
    all_files: list[str],
    repo_path: str,
    repo_name: str,
    log_planner_io: bool,
) -> list[SectionSpec]:
    scoped_files = _files_in_scope(all_files, group.scope_dirs)
    if not scoped_files:
        return []

    scoped_compressed = _scope_compressed(compressed, group.scope_dirs)
    context = _build_planner_context(
        dossier_dict=dossier_dict,
        compressed=scoped_compressed,
        all_files=scoped_files,
        repo_path=repo_path,
        repo_name=f"{repo_name} [{group.group_name}]",
    )
    system_prompt = GROUP_PLANNER_SYSTEM.format(
        group_name=group.group_name,
        expected_sections=max(1, group.expected_sections),
        boundary_hint=group.boundary_hint or "Keep sections within the scoped directories.",
    )
    if log_planner_io:
        logger.info("PLANNER_PHASE_B_SYSTEM(%s):\n%s", group.group_name, system_prompt)
        logger.info("PLANNER_PHASE_B_USER(%s):\n%s", group.group_name, context)

    response = model.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context},
    ])
    raw = response.content if hasattr(response, "content") else str(response)
    if log_planner_io:
        logger.info("PLANNER_PHASE_B_RAW(%s):\n%s", group.group_name, raw)

    parsed = _extract_json_dict(raw)
    sections = _parse_group_sections(parsed, group.group_name)
    fallback_files = scoped_files[:2]
    for section in sections:
        if not section.seed_files:
            section.seed_files = fallback_files.copy()
        if not section.menu_group:
            section.menu_group = group.group_name
        if not section.menu_label:
            section.menu_label = section.title
        if not section.boundary_hint:
            section.boundary_hint = group.boundary_hint
    return sections


def _extract_json_dict(raw: str) -> dict:
    cleaned = re.sub(r"```(?:json)?\s*", "", (raw or "")).replace("```", "").strip()
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m:
        cleaned = m.group(0)
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _parse_group_plans(data: dict, top_dirs: list[str]) -> list[MenuGroupPlan]:
    groups_raw = data.get("groups", []) if isinstance(data, dict) else []
    result: list[MenuGroupPlan] = []
    top_dir_set = set(top_dirs)
    for item in groups_raw:
        if not isinstance(item, dict):
            continue
        name = (item.get("group_name") or "").strip()
        if not name:
            continue
        scope = [d for d in (item.get("scope_dirs") or []) if isinstance(d, str) and d in top_dir_set]
        if not scope:
            continue
        expected = _safe_int(item.get("expected_sections", 2), default=2)
        expected = max(1, min(expected, 8))
        importance = (item.get("importance") or "supporting").lower()
        if importance not in {"core", "supporting", "peripheral"}:
            importance = "supporting"
        result.append(
            MenuGroupPlan(
                group_name=name,
                scope_dirs=scope,
                expected_sections=expected,
                boundary_hint=(item.get("boundary_hint") or "").strip(),
                importance=importance,
            )
        )
    return result


def _safe_int(value, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        s = str(value).strip()
        if not s:
            return default
        m = re.search(r"-?\d+", s)
        if not m:
            return default
        return int(m.group(0))
    except Exception:
        return default


def _top_level_stats(compressed: dict, all_files: list[str]) -> list[dict]:
    dir_summaries = compressed.get("directory_summaries", {}) or {}
    top_counts: Counter = Counter()
    top_langs: dict[str, Counter] = {}
    ext_lang = {
        ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
        ".jsx": "JavaScript", ".rs": "Rust", ".go": "Go", ".java": "Java", ".md": "Markdown",
    }
    for fp in all_files:
        top = _top_level_dir(fp)
        top_counts[top] += 1
        lang = ext_lang.get(Path(fp).suffix.lower(), Path(fp).suffix.lstrip(".").upper() or "Unknown")
        top_langs.setdefault(top, Counter())[lang] += 1

    top_summaries: dict[str, str] = {}
    for dir_path, info in dir_summaries.items():
        if not isinstance(info, dict):
            continue
        top = _top_level_dir(dir_path, assume_directory=True)
        if top not in top_summaries:
            top_summaries[top] = (info.get("summary", "") or "").strip()

    stats: list[dict] = []
    for top, count in top_counts.most_common():
        stats.append(
            {
                "top_dir": top,
                "file_count": count,
                "languages": [lang for lang, _ in top_langs.get(top, Counter()).most_common(4)],
                "summary": top_summaries.get(top, ""),
            }
        )
    return stats


def _structural_groups_fallback(stats: list[dict]) -> list[MenuGroupPlan]:
    if not stats:
        return []
    total = sum(s["file_count"] for s in stats) or 1
    groups: list[MenuGroupPlan] = []
    supporting_dirs: list[str] = []
    for s in stats:
        top = s["top_dir"]
        ratio = s["file_count"] / total
        if ratio >= 0.12 or s["file_count"] >= 120:
            groups.append(
                MenuGroupPlan(
                    group_name=f"{top} Architecture" if top != "." else "Root Architecture",
                    scope_dirs=[top],
                    expected_sections=max(2, min(5, s["file_count"] // 120 + 1)),
                    boundary_hint=f"Cover major architecture and flow under {top}.",
                    importance="core",
                )
            )
        else:
            supporting_dirs.append(top)
    if supporting_dirs:
        groups.append(
            MenuGroupPlan(
                group_name="Supporting Systems",
                scope_dirs=supporting_dirs,
                expected_sections=max(2, min(4, len(supporting_dirs) // 2 + 1)),
                boundary_hint="Cover supporting and peripheral modules without deep overlap.",
                importance="supporting",
            )
        )
    return groups


def _ensure_group_coverage(groups: list[MenuGroupPlan], top_dirs: list[str]) -> list[MenuGroupPlan]:
    covered: set[str] = set()
    for g in groups:
        covered.update(g.scope_dirs)
    for top in top_dirs:
        if top not in covered:
            groups.append(
                MenuGroupPlan(
                    group_name=f"{top} Modules" if top != "." else "Root Modules",
                    scope_dirs=[top],
                    expected_sections=1,
                    boundary_hint=f"Document modules under {top}.",
                    importance="supporting",
                )
            )
    return groups


def _files_in_scope(all_files: list[str], scope_dirs: list[str]) -> list[str]:
    if not scope_dirs:
        return []
    result: list[str] = []
    for fp in all_files:
        top = _top_level_dir(fp)
        if top in scope_dirs:
            result.append(fp)
    return result


def _scope_compressed(compressed: dict, scope_dirs: list[str]) -> dict:
    file_summaries = compressed.get("file_summaries", {}) or {}
    dir_summaries = compressed.get("directory_summaries", {}) or {}
    scoped_fs = {
        path: data for path, data in file_summaries.items()
        if _top_level_dir(path) in scope_dirs
    }
    scoped_ds = {
        path: data for path, data in dir_summaries.items()
        if _top_level_dir(path, assume_directory=True) in scope_dirs
    }
    scoped = dict(compressed)
    scoped["file_summaries"] = scoped_fs
    scoped["directory_summaries"] = scoped_ds
    # Prevent cross-group leakage in phase-B prompts.
    # Group planners should use scoped evidence only, not global nav skeleton.
    scoped["nav_plan"] = {}
    return scoped


def _parse_group_sections(data: dict, group_name: str) -> list[SectionSpec]:
    raw_sections = data.get("sections", []) if isinstance(data, dict) else []
    sections: list[SectionSpec] = []
    for item in raw_sections:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "home":
            continue
        section = SectionSpec.from_dict(item)
        section.seed_files = _coerce_list(section.seed_files)
        section.focus_tags = _coerce_list(section.focus_tags)
        section.cross_refs = _coerce_list(section.cross_refs)
        section.key_insights = _coerce_list(section.key_insights)
        section.menu_group = section.menu_group or group_name
        section.menu_label = section.menu_label or section.title
        if not section.slug:
            section.slug = _title_to_slug(section.title)
        sections.append(section)
    return sections


def _merge_group_sections(sections: list[SectionSpec]) -> list[SectionSpec]:
    if not sections:
        return []
    slot_map: dict[tuple[str, str], list[SectionSpec]] = {}
    for section in sections:
        key = (section.menu_group or "General", section.menu_label or section.title)
        slot_map.setdefault(key, []).append(section)

    merged: list[SectionSpec] = []
    for _, same_slot in slot_map.items():
        primary = same_slot[0]
        if len(same_slot) > 1:
            _absorb_into(primary, same_slot[1:])
        merged.append(primary)
    return merged


def _home_section(repo_name: str, compressed: dict) -> SectionSpec:
    nav_plan = compressed.get("nav_plan", {}) or {}
    raw_sections = nav_plan.get("sections", []) if isinstance(nav_plan, dict) else []
    for item in raw_sections:
        if isinstance(item, dict) and item.get("type") == "home":
            home = SectionSpec.from_dict(item)
            home.type = "home"
            home.menu_group = ""
            home.menu_label = ""
            if not home.slug:
                home.slug = "overview"
            if not home.title:
                home.title = "Overview"
            return home
    return SectionSpec(
        slug="overview",
        title="Overview",
        type="home",
        one_liner=f"Overview of the {repo_name} codebase.",
        focus_tags=["architecture"],
        seed_files=[],
    )


def _coerce_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str):
        v = value.strip()
        return [v] if v else []
    return [str(value)]


# ── Context builders ──────────────────────────────────────────────────────────

def _build_planner_context(
    dossier_dict: dict,
    compressed: dict,
    all_files: list[str],
    repo_path: str,
    repo_name: str,
) -> str:
    parts: list[str] = [f"# Codebase: {repo_name}\n"]

    # ── Nav plan from compression (primary skeleton) ─────────────────────
    nav_plan = compressed.get("nav_plan", {})
    if nav_plan and nav_plan.get("sections"):
        import json as _json
        parts.append(
            "## Pre-Computed Navigation Skeleton (from compression analysis)\n"
            "Use this as your STARTING POINT. Refine, merge, or split sections "
            "based on dossier findings below. Do NOT discard this skeleton — "
            "it was built from every file and directory in the repo.\n"
            + _json.dumps(nav_plan, indent=2)
            + "\n"
        )

    # Repo-level summary (no longer truncated — nav_plan provides structure)
    repo_summary = compressed.get("repo_summary", "")
    if repo_summary:
        parts.append(f"## Repo Summary\n{repo_summary}\n")

    # Call graph summary
    call_graph_summary = compressed.get("call_graph_summary", "")
    if call_graph_summary:
        parts.append(f"## Call Graph Overview\n{call_graph_summary}\n")

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

    # File tree structure
    file_tree = _build_file_tree(all_files, repo_path)
    if file_tree:
        parts.append(f"## File Tree\n{file_tree}\n")

    # Directory summaries first (prominent structural context)
    dir_summaries = compressed.get("directory_summaries", {})
    dir_lines = _directory_context_lines(dir_summaries, all_files)
    if dir_lines:
        parts.append("## Directory Context\n" + "\n".join(dir_lines) + "\n")

    # Per-file summaries — stratified sampling across top-level directories
    file_summaries = compressed.get("file_summaries", {})
    if file_summaries:
        budget = min(len(file_summaries), max(150, len(all_files) // 5))
        sampled = _stratified_file_sample(file_summaries, budget)
        fs_lines = []
        for fpath, fdata in sampled:
            entities = fdata.get("key_entities", [])
            exports = fdata.get("exported_symbols", [])
            lang = fdata.get("language", "")
            summary = fdata.get("summary", "")
            nav_topic = fdata.get("nav_topic", "")
            parts_list = [fpath]
            if lang:
                parts_list.append(f"({lang})")
            if nav_topic:
                parts_list.append(f"[nav: {nav_topic}]")
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


def _top_level_dir(path: str, assume_directory: bool = False) -> str:
    parts = [p for p in Path(path).parts if p not in {"", "."}]
    if not parts:
        return "."
    if len(parts) == 1 and not assume_directory:
        return "."
    return parts[0]


def _stratified_file_sample(file_summaries: dict, budget: int) -> list[tuple[str, dict]]:
    """Sample file summaries proportionally across top-level dirs."""
    if not file_summaries or budget <= 0:
        return []

    items = list(file_summaries.items())
    if budget >= len(items):
        return sorted(items, key=lambda kv: kv[0])

    buckets: dict[str, list[tuple[str, dict]]] = {}
    for path, fdata in items:
        buckets.setdefault(_top_level_dir(path), []).append((path, fdata))

    for bucket in buckets.values():
        bucket.sort(key=lambda kv: (-(kv[1].get("entity_count", 0) or 0), kv[0]))

    total = len(items)
    allocations: dict[str, int] = {}
    remainders: list[tuple[float, str]] = []
    for top, bucket in buckets.items():
        frac = (len(bucket) / total) * budget
        base = int(frac)
        allocations[top] = base
        remainders.append((frac - base, top))

    selected = sum(allocations.values())
    for top in sorted(buckets):
        if selected >= budget:
            break
        if allocations[top] == 0 and buckets[top]:
            allocations[top] = 1
            selected += 1

    if selected < budget:
        for _, top in sorted(remainders, reverse=True):
            if selected >= budget:
                break
            if allocations[top] < len(buckets[top]):
                allocations[top] += 1
                selected += 1

    if selected > budget:
        for top in sorted(allocations, key=lambda k: allocations[k], reverse=True):
            while selected > budget and allocations[top] > 0:
                allocations[top] -= 1
                selected -= 1

    result: list[tuple[str, dict]] = []
    for top in sorted(buckets):
        take = min(allocations.get(top, 0), len(buckets[top]))
        result.extend(buckets[top][:take])

    seen = {p for p, _ in result}
    if len(result) < budget:
        leftovers: list[tuple[str, dict]] = []
        for top in sorted(buckets):
            leftovers.extend([(p, d) for p, d in buckets[top] if p not in seen])
        leftovers.sort(key=lambda kv: (-(kv[1].get("entity_count", 0) or 0), kv[0]))
        result.extend(leftovers[: budget - len(result)])

    return result[:budget]


def _directory_context_lines(dir_summaries: dict, all_files: list[str]) -> list[str]:
    """Directory summaries or deterministic fallback synthesized from file tree."""
    lines: list[str] = []
    if dir_summaries:
        for dir_path, summary in sorted(dir_summaries.items()):
            s = summary.get("summary", "") if isinstance(summary, dict) else ""
            if s:
                lines.append(f"- {dir_path}: {s[:200]}")
        if lines:
            return lines

    # Fallback: synthesize from all_files when LLM dir summaries are absent.
    dir_counts: Counter = Counter()
    dir_lang_counts: dict[str, Counter] = {}
    dir_children: dict[str, Counter] = {}
    ext_lang = {
        ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
        ".jsx": "JavaScript", ".rs": "Rust", ".go": "Go", ".java": "Java", ".md": "Markdown",
    }
    for fp in all_files:
        p = Path(fp)
        parent = str(p.parent) if str(p.parent) != "." else "."
        dir_counts[parent] += 1
        lang = ext_lang.get(p.suffix.lower(), p.suffix.lstrip(".").upper() or "Unknown")
        dir_lang_counts.setdefault(parent, Counter())[lang] += 1
        if parent != ".":
            parts = parent.split("/")
            if len(parts) > 1:
                top = "/".join(parts[:-1])
                child = parts[-1]
                dir_children.setdefault(top, Counter())[child] += 1

    ranked = sorted(dir_counts.items(), key=lambda kv: kv[1], reverse=True)[:120]
    for dir_path, count in ranked:
        langs = dir_lang_counts.get(dir_path, Counter()).most_common(3)
        lang_summary = ", ".join(f"{n} {lang}" for lang, n in langs) if langs else "mixed files"
        child_counter = dir_children.get(dir_path, Counter())
        child_summary = ""
        if child_counter:
            top_children = ", ".join(name for name, _ in child_counter.most_common(4))
            child_summary = f"; subdirs: {top_children}"
        lines.append(f"- {dir_path} ({count} files): {lang_summary}{child_summary}")
    return lines


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

        if section.menu_group and not section.menu_label:
            # Safe default: derive child label from title when group is present.
            section.menu_label = section.title

        valid_sections.append(section)

    nav.sections = valid_sections
    return nav


def _ensure_menu_groups(nav: WikiNav) -> None:
    """Guarantee every non-home section has a menu_group.

    If the LLM omitted menu_group, derive one from the section type:
    concept/architecture → "Architecture", workflow → "Guides",
    reference → "Reference", otherwise "General".
    """
    TYPE_TO_GROUP = {
        "architecture": "Architecture",
        "concept": "Architecture",
        "workflow": "Guides",
        "reference": "Reference",
    }
    for section in nav.sections:
        if section.type == "home":
            continue
        if not section.menu_group:
            section.menu_group = TYPE_TO_GROUP.get(section.type, "General")
            logger.info(
                "Assigned default menu_group %r to section %r",
                section.menu_group, section.slug,
            )
        if not section.menu_label:
            section.menu_label = section.title


def _consolidate_sections(nav: WikiNav) -> None:
    """Smart consolidation of wiki sections into a clean sidebar taxonomy.

    Three phases:
    1. Merge sections sharing the exact same (menu_group, menu_label).
    2. Within each group, merge sections whose title words are a subset of
       another section's title (e.g. "UI Library" absorbs "UI Library API Layer").
    3. Within each group, merge clusters of 3+ sections sharing the same
       first significant word (e.g. 5 "UI *" sections → 1 combined section).
    """
    home = [s for s in nav.sections if s.type == "home"]
    others = [s for s in nav.sections if s.type != "home"]

    if not others:
        return

    # Phase 1: merge sections sharing (menu_group, menu_label)
    slot_map: dict[tuple[str, str], list] = {}
    for section in others:
        key = (section.menu_group or "", section.menu_label or section.title)
        slot_map.setdefault(key, []).append(section)

    merged: list = []
    for (group, label), sections in slot_map.items():
        primary = sections[0]
        if len(sections) > 1:
            _absorb_into(primary, sections[1:])
            logger.info(
                "Phase 1: merged %d sections under (%s / %s) → %r",
                len(sections), group, label, primary.slug,
            )
        merged.append(primary)

    p1_count = len(merged)
    if len(others) != p1_count:
        logger.info("Phase 1: %d → %d sections", len(others), p1_count)

    # Phase 2: within each group, merge by title containment
    by_group: dict[str, list] = {}
    for s in merged:
        by_group.setdefault(s.menu_group or "", []).append(s)

    phase2: list = []
    for group_name, group_sections in by_group.items():
        consolidated = _merge_by_title_containment(group_sections)
        phase2.extend(consolidated)

    p2_count = len(phase2)
    if p1_count != p2_count:
        logger.info("Phase 2 (title containment): %d → %d sections", p1_count, p2_count)

    # Phase 3: within each group, merge clusters sharing the same first word
    by_group2: dict[str, list] = {}
    for s in phase2:
        by_group2.setdefault(s.menu_group or "", []).append(s)

    final: list = []
    for group_name, group_sections in by_group2.items():
        consolidated = _merge_by_prefix_cluster(group_sections)
        final.extend(consolidated)

    p3_count = len(final)
    if p2_count != p3_count:
        logger.info("Phase 3 (prefix clustering): %d → %d sections", p2_count, p3_count)

    total_before = len(others)
    total_after = len(final)
    if total_before != total_after:
        logger.info(
            "Consolidation complete: %d → %d sections (merged %d)",
            total_before, total_after, total_before - total_after,
        )

    nav.sections = home + final


def _merge_by_title_containment(sections: list) -> list:
    """Within a group, merge sections whose title is contained in another's.

    "UI Library" absorbs "UI Library API Layer" because all words of the
    shorter title appear in the longer one. Requires the shorter title to
    have at least 2 words (prevents single-word titles from swallowing
    everything).
    """
    if len(sections) <= 1:
        return sections

    def _title_words(title: str) -> set[str]:
        stop = {"and", "the", "of", "for", "in", "a", "an", "&", "-", "–"}
        return {w.lower() for w in title.split() if w.lower() not in stop}

    # Sort by title word count ascending — shorter titles are "broader"
    indexed = list(enumerate(sections))
    absorbed: set[int] = set()

    for i, section_a in indexed:
        if i in absorbed:
            continue
        words_a = _title_words(section_a.title)
        if len(words_a) < 2:
            continue
        for j, section_b in indexed:
            if j in absorbed or j == i:
                continue
            words_b = _title_words(section_b.title)
            # A's words are a proper subset of B's → B is a specialization of A
            if words_a < words_b:
                _absorb_into(section_a, [section_b])
                absorbed.add(j)
                logger.info(
                    "Title containment: %r absorbed %r",
                    section_a.slug, section_b.slug,
                )

    return [s for i, s in indexed if i not in absorbed]


def _merge_by_prefix_cluster(sections: list) -> list:
    """Within a group, merge clusters of 3+ sections sharing the same first word.

    Handles cases where title containment can't merge because titles differ
    in structure (e.g. "UI Architecture", "UI Layout", "UI Components",
    "UI Subcomponents", "UI Library" all start with "UI").
    """
    if len(sections) <= 2:
        return sections

    stop = {"and", "the", "of", "for", "in", "a", "an", "&", "-", "–"}

    def _first_significant_word(title: str) -> str:
        for w in title.split():
            if w.lower() not in stop:
                return w.lower()
        return title.split()[0].lower() if title.split() else ""

    # Group by first significant word
    clusters: dict[str, list] = {}
    for section in sections:
        fw = _first_significant_word(section.title)
        clusters.setdefault(fw, []).append(section)

    result: list = []
    for first_word, cluster in clusters.items():
        if len(cluster) >= 3:
            primary = cluster[0]
            _absorb_into(primary, cluster[1:])
            result.append(primary)
            logger.info(
                "Prefix cluster '%s': merged %d sections → %r",
                first_word, len(cluster), primary.slug,
            )
        else:
            result.extend(cluster)

    return result


def _absorb_into(primary, others: list) -> None:
    """Merge others' data into primary section."""
    sub_titles = [s.title for s in others]
    primary.boundary_hint = (
        (primary.boundary_hint or "")
        + f" Also covers: {', '.join(sub_titles)}."
    ).strip()
    # Merge seed_files
    seen_files: set[str] = set(primary.seed_files or [])
    for s in others:
        for f in (s.seed_files or []):
            if f not in seen_files:
                primary.seed_files.append(f)
                seen_files.add(f)
    # Merge focus_tags
    seen_tags: set[str] = set(primary.focus_tags or [])
    for s in others:
        for t in (s.focus_tags or []):
            if t not in seen_tags:
                primary.focus_tags.append(t)
                seen_tags.add(t)
    # Merge cross_refs
    seen_refs: set[str] = set(primary.cross_refs or [])
    for s in others:
        for r in (s.cross_refs or []):
            if r not in seen_refs:
                if not primary.cross_refs:
                    primary.cross_refs = []
                primary.cross_refs.append(r)
                seen_refs.add(r)
    # Merge key_insights (deduplicate by exact match)
    seen_insights: set[str] = set(primary.key_insights or [])
    for s in others:
        for insight in (s.key_insights or []):
            if insight not in seen_insights:
                if not primary.key_insights:
                    primary.key_insights = []
                primary.key_insights.append(insight)
                seen_insights.add(insight)


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
