"""PLANNER agent — organizes wiki sections by architectural components.

Uses the ArchitectureModel from ARCHITECT to create a WikiPlan where
sections map to components and relevant_files come from component_map
(deterministic, not LLM-guessed).
"""

import json
import logging
import re
import time

from src.llm.client import chat
from src.wiki.agents.graph import report_agent_progress
from src.wiki.agents.state import ArchitectureModel, WikiState

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are a senior software architect organizing a wiki for a codebase.

Your goal is to create a "Guided Tour" of the codebase architecture, not a directory listing.
Organize sections by FUNCTIONAL THEMES and ARCHITECTURAL CONCEPTS (e.g., "The Handoff Mechanism", "Agent Orchestration", "Security & Guardrails") 
rather than directory names (e.g., "src/agents", "backend/airline").

Output ONLY valid JSON with this structure:
{
  "title": "Project Name — Documentation",
  "sections": [
    {
      "id": "url-slug",
      "title": "Architecture-First Title (e.g., The Handoff Flow)",
      "maps_to_components": ["Exact Component Name from the architecture"],
      "subsections": [
        {
          "id": "sub-slug",
          "title": "Subsection Title",
          "describes": "What this subsection explains",
          "relevant_entities": ["module.ClassName"]
        }
      ],
      "diagram_type": "architecture|flowchart|sequence|class",
      "table_type": "components|apis|tools|none"
    }
  ]
}

Guidelines:
- Create 5-10 sections that represent the "Chapters" of a developer's mental model
- CRITICAL: Group related files by their logical role (e.g., group the Frontend Agent Panel with the Backend Agent Logic in a "User Interaction & Agent State" chapter)
- Section IDs must be valid URL slugs (lowercase, hyphens, no spaces)

SECTION QUALITY:
- You MUST include a diagram_type for EVERY section.
- For sections involving multiple agents, handoffs, or request/response flows, ALWAYS use "sequence".
- For sections describing core structure or data models, use "architecture" or "class".
- For sections describing complex logic flows or state machines, use "flowchart".
- The 'describes' field should be detailed (2-3 sentences guiding the writer)
- Every architectural component should be covered by at least one section"""


def planner_node(state: WikiState) -> dict:
    """PLANNER node — create wiki section plan from architecture."""
    t0 = time.monotonic()
    logger.info("PLANNER agent starting")
    report_agent_progress("planner", "running", "Planning wiki sections")

    architecture = state.get("architecture", {})
    fingerprint = state.get("fingerprint", {})
    all_files = state.get("all_files", [])
    entity_index = state.get("entity_index", {})

    arch = ArchitectureModel.from_dict(architecture)

    # Build rich context from architecture
    context_parts = []

    # Components
    if arch.components:
        comp_lines = []
        for c in arch.components:
            deps = ", ".join(c.get("dependencies", [])) or "none"
            files = c.get("files", [])
            comp_lines.append(
                f"  - {c['name']}: {c.get('purpose', '')}\n"
                f"    Files: {', '.join(files[:10])}\n"
                f"    Dependencies: {deps}"
            )
        context_parts.append(
            "## Components\n" + "\n".join(comp_lines)
        )

    # Layers
    if arch.layers:
        layer_lines = [
            f"  - {l['name']}: {l.get('purpose', '')}"
            for l in arch.layers
        ]
        context_parts.append(
            "## Layers\n" + "\n".join(layer_lines)
        )

    # Data flows
    if arch.data_flows:
        flow_lines = [
            f"  - {f['source']} → {f['destination']}: {f.get('description', '')}"
            for f in arch.data_flows
        ]
        context_parts.append(
            "## Data Flows\n" + "\n".join(flow_lines)
        )

    # Key abstractions
    if arch.key_abstractions:
        context_parts.append(
            "## Key Abstractions\n"
            + "\n".join(f"  - {a}" for a in arch.key_abstractions)
        )

    # Project metadata
    proj_name = fingerprint.get("project_name", "Project")
    context_parts.append(
        f"## Project: {proj_name}\n"
        f"Files: {len(all_files)}, "
        f"Type: {fingerprint.get('system_type', 'unknown')}"
    )

    full_context = "\n\n".join(context_parts)

    prompt = f"""Plan the wiki sections for this codebase.

{full_context}

Create sections that map to the architectural components.
Output ONLY valid JSON matching the schema above."""

    try:
        response = chat(
            [
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=8192,
            temperature=0.2,
            cache_ttl=3600,
        )

        plan = _parse_plan_response(response, arch, all_files, entity_index)
    except Exception as exc:
        logger.error("PLANNER agent failed: %s", exc)
        plan = _fallback_plan(arch, fingerprint, all_files, entity_index)

    elapsed = time.monotonic() - t0
    n_sections = len(plan.get("sections", []))
    logger.info(
        "PLANNER agent complete: %d sections (%.1fs)",
        n_sections, elapsed,
    )
    report_agent_progress("planner", "complete", f"{n_sections} sections planned")

    return {
        "plan": plan,
        "agent_results": [{
            "agent": "planner",
            "success": True,
            "elapsed": elapsed,
            "sections": len(plan.get("sections", [])),
        }],
    }


def _parse_plan_response(
    response: str,
    arch: ArchitectureModel,
    all_files: list,
    entity_index: dict,
) -> dict:
    """Parse LLM response into WikiPlan-compatible dict."""
    text = response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning("PLANNER: Could not parse JSON response")
                return _fallback_plan(arch, {}, all_files, entity_index)
        else:
            return _fallback_plan(arch, {}, all_files, entity_index)

    # Enrich sections with file mappings from architecture
    sections = data.get("sections", [])
    for section in sections:
        _enrich_section_files(section, arch, entity_index)

    # Calculate coverage and distribute uncovered files
    covered_files = set()
    for section in sections:
        for sub in section.get("subsections", []):
            covered_files.update(sub.get("relevant_files", []))

    uncovered = [f for f in all_files if f not in covered_files]

    # Distribute uncovered files to sections by directory proximity
    if uncovered and sections:
        _distribute_uncovered_files(sections, uncovered, entity_index)
        # Recalculate
        covered_files = set()
        for section in sections:
            for sub in section.get("subsections", []):
                covered_files.update(sub.get("relevant_files", []))
        uncovered = [f for f in all_files if f not in covered_files]

    coverage_pct = (len(covered_files) / len(all_files) * 100) if all_files else 0
    logger.info(
        "PLANNER: File coverage: %d/%d (%.0f%%), %d uncovered",
        len(covered_files), len(all_files), coverage_pct, len(uncovered),
    )

    data["total_files_covered"] = len(covered_files)
    data["uncovered_files"] = uncovered

    return data


def _enrich_section_files(
    section: dict,
    arch: ArchitectureModel,
    entity_index: dict,
) -> None:
    """Add relevant_files to subsections using maps_to_components from LLM output.

    Strategy:
      1. Use maps_to_components field (exact component name match) — most reliable
      2. Fall back to word-overlap scoring between section title and component names
      3. Use component_map to gather all files belonging to matched components
    """
    mapped_names = section.get("maps_to_components", [])

    # Build component name → files lookup
    comp_files: dict[str, list[str]] = {}
    for comp in arch.components:
        comp_files[comp["name"]] = comp.get("files", [])

    # Also build reverse map: component_name → files from component_map
    comp_map_files: dict[str, list[str]] = {}
    for file_path, comp_name in arch.component_map.items():
        comp_map_files.setdefault(comp_name, []).append(file_path)

    matching_files: list[str] = []
    matched_components: set[str] = set()

    # Strategy 1: Use maps_to_components (exact match)
    for mapped in mapped_names:
        mapped_lower = mapped.strip().lower()
        for comp_name, files in comp_files.items():
            if comp_name.lower() == mapped_lower:
                matching_files.extend(files)
                matched_components.add(comp_name)
        # Also check component_map names
        for comp_name, files in comp_map_files.items():
            if comp_name.lower() == mapped_lower and comp_name not in matched_components:
                matching_files.extend(files)
                matched_components.add(comp_name)

    # Strategy 2: Word-overlap scoring (fallback when maps_to_components misses)
    if not matching_files:
        section_title = section.get("title", "")
        section_words = set(_tokenize(section_title))
        if section_words:
            scored: list[tuple[float, str, list[str]]] = []
            for comp_name, files in comp_files.items():
                comp_words = set(_tokenize(comp_name))
                if not comp_words:
                    continue
                overlap = len(section_words & comp_words)
                union = len(section_words | comp_words)
                score = overlap / union if union else 0
                if score > 0.15:  # At least some word overlap
                    scored.append((score, comp_name, files))

            scored.sort(reverse=True)
            for score, comp_name, files in scored[:2]:  # Take top 2 matches
                matching_files.extend(files)
                matched_components.add(comp_name)
                logger.debug(
                    "PLANNER: Fuzzy matched section '%s' → component '%s' (score=%.2f)",
                    section_title, comp_name, score,
                )

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_files: list[str] = []
    for f in matching_files:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)
    matching_files = unique_files

    # Distribute files across subsections
    subsections = section.get("subsections", [])
    if subsections and matching_files:
        files_per_sub = max(1, len(matching_files) // len(subsections))
        for i, sub in enumerate(subsections):
            start = i * files_per_sub
            end = start + files_per_sub if i < len(subsections) - 1 else len(matching_files)
            sub.setdefault("relevant_files", []).extend(matching_files[start:end])

            # Add entity qnames for files in this subsection
            sub_files = set(sub.get("relevant_files", []))
            for qname, info in entity_index.items():
                if info.get("file_path") in sub_files:
                    sub.setdefault("relevant_entities", []).append(qname)
    elif matching_files:
        # No subsections — create a default subsection with all files
        slug = section.get("id", "section")
        section["subsections"] = [{
            "id": f"{slug}-overview",
            "title": f"{section.get('title', 'Overview')}",
            "describes": f"Overview of {section.get('title', 'this section')}",
            "relevant_files": matching_files,
            "relevant_entities": [
                qn for qn, info in entity_index.items()
                if info.get("file_path") in set(matching_files)
            ][:50],
        }]

    if not matching_files:
        logger.warning(
            "PLANNER: Section '%s' matched 0 files (maps_to_components=%s)",
            section.get("title", "?"), mapped_names,
        )


def _tokenize(text: str) -> list[str]:
    """Tokenize a title into lowercase words, stripping common stop words."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    stop = {"the", "a", "an", "and", "or", "of", "for", "in", "to", "with", "is", "are"}
    return [w for w in words if w not in stop and len(w) > 1]


def _distribute_uncovered_files(
    sections: list[dict],
    uncovered: list[str],
    entity_index: dict,
    max_files_per_section: int = 40,
) -> None:
    """Assign uncovered files to sections by directory proximity, with a cap per section."""
    import os
    # Build section → existing file dirs map and current file count
    section_dirs: list[tuple[int, set[str]]] = []
    section_file_counts: dict[int, int] = {}
    for i, section in enumerate(sections):
        dirs: set[str] = set()
        count = 0
        for sub in section.get("subsections", []):
            files = sub.get("relevant_files", [])
            count += len(files)
            for f in files:
                dirs.add(os.path.dirname(f))
        section_dirs.append((i, dirs))
        section_file_counts[i] = count

    for filepath in uncovered:
        file_dir = os.path.dirname(filepath)

        # Score all sections by directory proximity, respecting the cap
        candidates: list[tuple[int, int]] = []
        for idx, dirs in section_dirs:
            if section_file_counts[idx] >= max_files_per_section:
                continue
            overlap = sum(1 for d in dirs if file_dir.startswith(d) or d.startswith(file_dir))
            candidates.append((overlap, idx))

        if not candidates:
            # All sections at cap — find the one with fewest files
            best_idx = min(section_file_counts, key=section_file_counts.get)
        else:
            candidates.sort(reverse=True)
            best_idx = candidates[0][1]

        # Add to last subsection of best-matching section
        section = sections[best_idx]
        subs = section.get("subsections", [])
        if subs:
            subs[-1].setdefault("relevant_files", []).append(filepath)
        else:
            slug = section.get("id", "section")
            section["subsections"] = [{
                "id": f"{slug}-misc",
                "title": f"{section.get('title', 'Other')} Files",
                "describes": "Additional files in this area",
                "relevant_files": [filepath],
                "relevant_entities": [],
            }]
        section_file_counts[best_idx] += 1


def _fallback_plan(
    arch: ArchitectureModel,
    fingerprint: dict,
    all_files: list,
    entity_index: dict,
) -> dict:
    """Generate a plan directly from architecture components."""
    proj_name = fingerprint.get("project_name", "Project")

    sections = []
    covered = set()

    for comp in arch.components:
        slug = re.sub(r"[^a-z0-9]+", "-", comp["name"].lower()).strip("-")
        files = comp.get("files", [])
        covered.update(files)

        # Create subsections from file groups
        subsections = []
        if files:
            subsections.append({
                "id": f"{slug}-overview",
                "title": f"{comp['name']} Overview",
                "describes": comp.get("purpose", f"Overview of {comp['name']}"),
                "relevant_files": files,
                "relevant_entities": [
                    qn for qn, info in entity_index.items()
                    if info.get("file_path") in set(files)
                ][:50],
            })

        sections.append({
            "id": slug,
            "title": comp["name"],
            "subsections": subsections,
            "diagram_type": "architecture" if len(files) > 2 else "none",
            "table_type": "components" if len(files) > 1 else "none",
        })

    return {
        "title": f"{proj_name} — Documentation",
        "sections": sections,
        "total_files_covered": len(covered),
        "uncovered_files": [f for f in all_files if f not in covered],
    }
