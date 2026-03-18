"""WRITER agent — generates pure prose for each wiki section.

Produces clean technical writing with [[heading:...]] and [[code:...]] markers
but NO entity markers (those are added by ANNOTATOR). Spawns parallel LLM calls
per section.
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.llm.client import chat
from src.wiki.agents.graph import report_agent_progress
from src.wiki.agents.state import ArchitectureModel, WikiState

logger = logging.getLogger(__name__)

WRITER_SYSTEM_PROMPT = """You are a senior technical writer creating comprehensive wiki documentation for a software codebase.

Write professional, detailed prose that explains WHY components exist, not just WHAT they do.
Your prose should help a new developer deeply understand the codebase architecture, design decisions, and integration points.

CONTENT REQUIREMENTS:
1. Explain the purpose and motivation behind each component
2. Describe design decisions and trade-offs made
3. Be CONCISE and PUNCHY — avoid fluff and repetition
4. Use SHORT PARAGRAPHS (2-4 sentences max)
5. Use BULLET POINTS liberally for lists of features or steps
6. Cover error handling strategies and edge cases briefly
7. Explain how components integrate with each other
8. Reference specific functions, classes, and patterns from the source code
9. Note any gotchas, caveats, or non-obvious behaviors
10. Aim for clarity over quantity — documentation should be "easily digestible in a few mins"

FORMATTING RULES:
1. Use [[heading:2:Title]] for section headings and [[heading:3:Title]] for sub-headings
2. Use headings FREQUENTLY to break up the text (one heading every 2-3 paragraphs)
3. Use [[code:filepath:start_line:end_line]] to embed actual source code inline
3. Do NOT use markdown headings (# or ##) — use [[heading:...]] markers
4. Do NOT use ```code fences``` — use [[code:...]] markers
5. Do NOT use [[entity:...]] markers — those will be added later
6. Write flowing prose paragraphs with frequent code references via [[code:...]] markers
7. Explain architectural decisions, patterns, and data flows in depth
8. Aim for a high density of code snippets — use [[code:...]] for every major class, function, or data structure you explain (target: 3-5 snippets per section)
9. Ensure start_line and end_line are accurate based on the source context provided"""


def writer_node(state: WikiState) -> dict:
    """WRITER node — generate prose for all sections in parallel."""
    t0 = time.monotonic()
    logger.info("WRITER agent starting")
    report_agent_progress("writer", "running", "Writing technical prose")

    plan = state.get("plan", {})
    architecture = state.get("architecture", {})
    compressed = state.get("compressed", {})
    repo_path = state.get("repo_path", "")
    entities = state.get("entities", [])
    dossier = state.get("dossier", {})
    entity_index = state.get("entity_index", {})

    arch = ArchitectureModel.from_dict(architecture)
    sections = plan.get("sections", [])

    # 1. Generate system narrative
    system_narrative = _generate_system_narrative(
        plan, arch, compressed, dossier,
    )

    # 2. Generate section content in parallel
    narrated_sections = {}

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {}
        for section in sections:
            future = pool.submit(
                _write_section,
                section, system_narrative, arch, compressed,
                repo_path, entities, entity_index, dossier, plan,
            )
            futures[future] = section

        for future in as_completed(futures):
            section = futures[future]
            section_id = section.get("id", "unknown")
            try:
                result = future.result(timeout=300)
                narrated_sections[section_id] = result
                logger.info("WRITER: completed section '%s'", section.get("title"))
            except Exception as exc:
                logger.error("WRITER: section '%s' failed: %s", section.get("title"), exc)
                narrated_sections[section_id] = {
                    "section_id": section_id,
                    "title": section.get("title", section_id),
                    "prose": f"Documentation for {section.get('title', section_id)} is being generated.",
                    "subsections": [],
                }

    elapsed = time.monotonic() - t0
    n_sections = len(narrated_sections)
    n_words = len(system_narrative.split())
    logger.info(
        "WRITER agent complete: %d sections, narrative=%d words (%.1fs)",
        n_sections, n_words, elapsed,
    )
    report_agent_progress("writer", "complete", f"{n_sections} sections, {n_words} words")

    return {
        "system_narrative": system_narrative,
        "narrated_sections": narrated_sections,
        "agent_results": [{
            "agent": "writer",
            "success": True,
            "elapsed": elapsed,
            "sections": len(narrated_sections),
            "narrative_words": len(system_narrative.split()),
        }],
    }


def _generate_system_narrative(
    plan: dict,
    arch: ArchitectureModel,
    compressed: dict,
    dossier: dict,
) -> str:
    """Generate 500-1000 word cross-cutting overview."""
    section_titles = [s.get("title", "") for s in plan.get("sections", [])]
    repo_summary = compressed.get("repo_summary", "")

    # Build architecture context
    arch_context = ""
    if arch.components:
        comp_summary = ", ".join(c["name"] for c in arch.components[:8])
        arch_context = f"\nArchitectural components: {comp_summary}"
    if arch.key_abstractions:
        arch_context += f"\nKey concepts: {', '.join(arch.key_abstractions[:8])}"
    if arch.data_flows:
        flows = [f"{f['source']} → {f['destination']}" for f in arch.data_flows[:5]]
        arch_context += f"\nData flows: {'; '.join(flows)}"

    prompt = f"""Write a comprehensive technical overview of this codebase (1000-2000 words).
This will be the introduction to the wiki documentation.

{repo_summary}
{arch_context}

The documentation is organized into these sections:
{chr(10).join(f'  - {t}' for t in section_titles)}

Write in a professional, informative tone. Use these formatting rules:
1. Divide the content into clear sections using "## Section Title" (Markdown style).
2. Use bullet points and numbered lists liberally.
3. Explain:
   - What the project does and its core purpose.
   - The high-level architecture and how components interact.
   - The key design decisions and patterns used.
   - A "Codebase Navigation" guide for newcomers.
4. Reference sections by name where relevant.
5. Aim for 3-5 sentences per paragraph maximum.

Write the overview now."""

    try:
        narrative = chat(
            [{"role": "user", "content": prompt}],
            max_tokens=6000,
            temperature=0.4,
            cache_ttl=3600,
        ).strip()
        
        # Convert ## / ### / #### headings to [[heading:level:Title]] markers
        def _heading_replacer(m: re.Match) -> str:
            level = len(m.group(1))
            title = m.group(2).strip()
            return f"[[heading:{level}:{title}]]"

        narrative = re.sub(r"^(#{2,4})\s+(.+)$", _heading_replacer, narrative, flags=re.MULTILINE)
        return narrative
    except Exception as exc:
        logger.error("System narrative failed: %s", exc)
        return repo_summary or "Project documentation overview."


def _write_section(
    section: dict,
    system_narrative: str,
    arch: ArchitectureModel,
    compressed: dict,
    repo_path: str,
    entities: list,
    entity_index: dict,
    dossier: dict,
    plan: dict,
) -> dict:
    """Write prose for a single section."""
    section_id = section.get("id", "unknown")
    section_title = section.get("title", section_id)

    # Gather files for this section from subsections (capped to prevent overload)
    section_files = _get_section_files(section)
    if len(section_files) > 30:
        logger.info("WRITER: Capping section '%s' files from %d to 30", section_title, len(section_files))
        section_files = section_files[:30]

    # Find matching architecture component(s)
    component_context = _get_component_context(section, arch)

    # Build source context (tiered by file size)
    source_context = _build_source_context(
        section_files, repo_path, entities, entity_index, compressed,
    )

    # Subsection guide
    subsection_guide = ""
    subsections = section.get("subsections", [])
    if subsections:
        sub_lines = [
            f"  - {s.get('title', '')}: {s.get('describes', '')}"
            for s in subsections
        ]
        subsection_guide = (
            "Organize your content to cover these subsections:\n"
            + "\n".join(sub_lines)
        )

    # Cross-reference targets
    other_sections = [
        s.get("title", "")
        for s in plan.get("sections", [])
        if s.get("id") != section_id
    ]

    prompt = f"""Write comprehensive, in-depth technical documentation for the "{section_title}" section.
Be thorough — cover design decisions, error handling, integration points, and configuration.
Do NOT artificially limit length. Write as much as needed to fully explain this section.

System overview (for context, don't repeat):
{system_narrative[:1500]}

{component_context}

{subsection_guide}

Source code context:
{source_context[:80000]}

FORMATTING RULES:
1. Use [[heading:2:Title]] for section headings and [[heading:3:Title]] for sub-headings
2. Use [[code:filepath:start_line:end_line]] to embed source code snippets
3. Do NOT use [[entity:...]] markers — those will be added by a separate agent
4. Do NOT use markdown headings (# / ##) or code fences (```)
5. Write professional prose explaining WHY, not just WHAT
6. Reference specific functions, classes, and patterns from the source code
7. Use [[code:filepath:start_line:end_line]] LIBERALLY to embed important source code inline
8. Cover error handling, edge cases, configuration, and integration points
9. Mention related sections by name: {', '.join(other_sections[:5])}

Write comprehensive section content now. Be thorough and detailed."""

    try:
        prose = chat(
            [
                {"role": "system", "content": WRITER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=8192,
            temperature=0.4,
            cache_ttl=3600,
        ).strip()
    except Exception as exc:
        logger.error("WRITER: section '%s' failed: %s", section_title, exc)
        prose = f"Documentation for {section_title} is being generated."

    # Strip leading title if it matches section title
    prose = _strip_leading_title(prose, section_title)

    # Extract subsection headings from the prose
    detected_subsections = []
    for match in re.finditer(r"\[\[heading:(\d+):([^\]]+)\]\]", prose):
        level = int(match.group(1))
        title = match.group(2).strip()
        sub_id = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        detected_subsections.append({"id": sub_id, "title": title, "level": level})

    return {
        "section_id": section_id,
        "title": section_title,
        "prose": prose,
        "subsections": detected_subsections,
    }


def _get_section_files(section: dict) -> list[str]:
    """Collect all files for a section from subsections."""
    files: list[str] = []
    seen: set[str] = set()
    for sub in section.get("subsections", []):
        for f in sub.get("relevant_files", []):
            if f not in seen:
                seen.add(f)
                files.append(f)
    # Also check section-level files
    for f in section.get("_all_files", []):
        if f not in seen:
            seen.add(f)
            files.append(f)
    return files


def _get_component_context(section: dict, arch: ArchitectureModel) -> str:
    """Find matching architecture component(s) using maps_to_components or section files."""
    mapped_names = section.get("maps_to_components", [])
    section_title = section.get("title", "")

    matched_comps = []

    # Strategy 1: Use maps_to_components (set by planner)
    for mapped in mapped_names:
        mapped_lower = mapped.strip().lower()
        for comp in arch.components:
            if comp.get("name", "").lower() == mapped_lower:
                matched_comps.append(comp)

    # Strategy 2: Match by section files
    if not matched_comps:
        section_files = set()
        for sub in section.get("subsections", []):
            section_files.update(sub.get("relevant_files", []))

        if section_files:
            # Find components whose files overlap with section files
            for comp in arch.components:
                comp_files = set(comp.get("files", []))
                if comp_files & section_files:
                    matched_comps.append(comp)

    if not matched_comps:
        return ""

    parts = ["Architecture context:"]
    for comp in matched_comps[:3]:
        deps = ", ".join(comp.get("dependencies", [])) or "none"
        interfaces = ", ".join(comp.get("public_interfaces", [])[:10]) or "none"
        parts.append(
            f"  Component: {comp.get('name', '')}\n"
            f"  Purpose: {comp.get('purpose', '')}\n"
            f"  Dependencies: {deps}\n"
            f"  Public interfaces: {interfaces}"
        )
    return "\n".join(parts)


def _build_source_context(
    section_files: list[str],
    repo_path: str,
    entities: list,
    entity_index: dict,
    compressed: dict,
    max_chars: int = 80000,
) -> str:
    """Build source context tiered by file size.

    - <200 lines: include full file content
    - 200-1000 lines: include top entities + file summary
    - >1000 lines: include entity signatures + docstrings only
    """
    file_summaries = compressed.get("file_summaries", {})

    # Index entities by file
    file_entities: dict[str, list] = {}
    for e in entities:
        fp = getattr(e, "file_path", None) or (e.get("file_path") if isinstance(e, dict) else None)
        if fp and fp in set(section_files):
            file_entities.setdefault(fp, []).append(e)

    parts: list[str] = []
    chars_used = 0

    for fp in section_files:
        if chars_used >= max_chars:
            break

        full_path = Path(repo_path) / fp
        fs = file_summaries.get(fp)

        try:
            if full_path.is_file():
                lines = full_path.read_text(errors="replace").splitlines()
                line_count = len(lines)
            else:
                line_count = 0
                lines = []
        except Exception:
            line_count = 0
            lines = []

        budget = max_chars - chars_used

        if line_count < 200 and lines:
            content = "\n".join(lines)
            if len(content) > budget:
                content = content[:budget]
            part = f"\n--- {fp} (full file, {line_count} lines) ---\n{content}"
        elif line_count < 1000:
            part_lines = [f"\n--- {fp} ({line_count} lines) ---"]
            if fs:
                summary = fs.get("summary", "") if isinstance(fs, dict) else str(fs)
                part_lines.append(f"Summary: {summary}")
            for e in file_entities.get(fp, [])[:10]:
                ls = getattr(e, "line_start", None) or (e.get("line_start") if isinstance(e, dict) else None)
                le = getattr(e, "line_end", None) or (e.get("line_end") if isinstance(e, dict) else None)
                qn = getattr(e, "qualified_name", None) or (e.get("qualified_name") if isinstance(e, dict) else "?")
                et = getattr(e, "entity_type", None) or (e.get("entity_type") if isinstance(e, dict) else "")
                if ls and le and lines:
                    body = "\n".join(lines[max(0, ls - 1):min(le, len(lines))])
                    if len(body) < 2000:
                        part_lines.append(f"\n{et} {qn}:\n{body}")
                    else:
                        sig = getattr(e, "signature", None) or (e.get("signature") if isinstance(e, dict) else "")
                        part_lines.append(f"\n{et} {qn}: {sig or qn}")
            part = "\n".join(part_lines)
        else:
            part_lines = [f"\n--- {fp} ({line_count} lines, large file) ---"]
            if fs:
                summary = fs.get("summary", "") if isinstance(fs, dict) else str(fs)
                part_lines.append(f"Summary: {summary}")
            for e in file_entities.get(fp, [])[:15]:
                qn = getattr(e, "qualified_name", None) or (e.get("qualified_name") if isinstance(e, dict) else "?")
                et = getattr(e, "entity_type", None) or (e.get("entity_type") if isinstance(e, dict) else "")
                sig = getattr(e, "signature", None) or (e.get("signature") if isinstance(e, dict) else "")
                doc = getattr(e, "docstring", None) or (e.get("docstring") if isinstance(e, dict) else "")
                doc_preview = f" — {doc[:100]}" if doc else ""
                part_lines.append(f"  {et} {qn}: {sig or qn}{doc_preview}")
            part = "\n".join(part_lines)

        if len(part) > budget:
            part = part[:budget]

        parts.append(part)
        chars_used += len(part)

    return "\n".join(parts)


def _strip_leading_title(prose: str, section_title: str) -> str:
    """Strip leading '# Title' if it matches the section title."""
    lines = prose.split("\n", 1)
    first = lines[0].strip()
    if first.startswith("#"):
        heading_text = first.lstrip("#").strip()
        normalized_heading = re.sub(r"[^a-z0-9]", "", heading_text.lower())
        normalized_title = re.sub(r"[^a-z0-9]", "", section_title.lower())
        if normalized_heading == normalized_title:
            return lines[1].lstrip("\n") if len(lines) > 1 else ""
    return prose
