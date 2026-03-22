"""Phase 2: Content generation.

Generates rich prose for each wiki section using LLM calls.
The prose includes [[marker]] patterns that Phase 3 (enricher)
resolves into structured segments:
  [[entity:QualifiedName]]  → source link
  [[section:slug]]          → cross-section link
  [[code:filepath:start:end]] → embedded code block
"""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from src.llm.client import chat
from src.parsers.base import ParsedEntity
from src.wiki.v2_types import (
    CompressedCodebase,
    NarratedSection,
    WikiPlan,
    WikiSectionPlan,
)

logger = logging.getLogger(__name__)


def generate_system_narrative(
    compressed: CompressedCodebase,
    plan: WikiPlan,
    dossier=None,
) -> str:
    """Generate a 500-1000 word cross-cutting overview.

    This narrative provides context that individual sections reference.
    """
    section_titles = [s.title for s in plan.sections]

    # Build architecture context from dossier
    arch_context = ""
    arch = dossier.sections.get("architecture") if dossier else None
    if arch:
        arch_context = (
            f"\nArchitecture: {arch.primary_style} "
            f"(patterns: {', '.join(arch.patterns_detected[:5])})"
        )

    prompt = f"""Write a comprehensive technical overview of this codebase (1000-2000 words).
This will be the introduction to the wiki documentation.

Project: {plan.title}
{compressed.repo_summary[:1500]}

The documentation is organized into these sections:
{chr(10).join(f'  - {t}' for t in section_titles)}
{arch_context}

Write in a professional, informative tone. Use these formatting rules:
1. Divide the content into clear sections using "## Section Title" (Markdown style).
2. Use bullet points and numbered lists to break up long lists of features or components.
3. Explain:
   - What the project does and its core purpose.
   - The high-level architecture and how components interact.
   - The key design decisions and patterns used.
   - A "Codebase Navigation" guide for newcomers.
4. Reference sections by name where relevant.
5. AVOID long, dense paragraphs. Aim for 3-5 sentences per paragraph maximum.

Write the overview now."""

    try:
        narrative = chat(
            [{"role": "user", "content": prompt}],
            max_tokens=6000,
            temperature=0.4,
            cache_ttl=3600,
        )
        # Convert ## / ### / #### headings to [[heading:level:Title]] markers
        def _heading_replacer(m: re.Match) -> str:
            level = len(m.group(1))
            title = m.group(2).strip()
            return f"[[heading:{level}:{title}]]"

        narrative = re.sub(r"^(#{2,4})\s+(.+)$", _heading_replacer, narrative, flags=re.MULTILINE)
        return narrative.strip()
    except Exception as exc:
        logger.error("System narrative generation failed: %s", exc)
        return compressed.repo_summary


def generate_section_content(
    section: WikiSectionPlan,
    system_narrative: str,
    compressed: CompressedCodebase,
    plan: WikiPlan,
    repo_path: str,
    entities: list[ParsedEntity],
    dossier=None,
) -> NarratedSection:
    """Generate content for a single wiki section.

    One LLM call producing 500-1500 words with marker annotations.
    """
    # Build source context (tiered by file size)
    source_context = _build_source_context(
        section, repo_path, entities, compressed, max_chars=50000,
    )

    # Get dossier RAG findings for this section's files
    dossier_context = ""
    if dossier:
        dossier_context = _get_dossier_context(section, dossier)

    # Collect entity names available for this section (for prompt guidance)
    section_entity_names: list[str] = []
    section_files_set = set(section.all_relevant_files)
    for e in entities:
        if e.name.startswith("_"):
            continue
        if e.file_path in section_files_set:
            section_entity_names.append(e.qualified_name)

    entity_list_text = ""
    if section_entity_names:
        entity_list_text = (
            f"\nAvailable entities for this section (use [[entity:QualifiedName]] markers to reference them):\n"
            + "\n".join(f"  - {qn}" for qn in section_entity_names[:300])
        )

    # Other section titles for cross-referencing
    other_sections = [
        f"  - [[section:{s.id}]] ({s.title})"
        for s in plan.sections
        if s.id != section.id
    ]

    # Subsection guidance
    subsection_guide = ""
    if section.subsections:
        sub_lines = []
        for sub in section.subsections:
            sub_lines.append(f"  - {sub.title}: {sub.describes}")
        subsection_guide = (
            "Organize your content to cover these subsections:\n"
            + "\n".join(sub_lines)
        )

    prompt = f"""Write detailed technical documentation (500-1500 words) for the "{section.title}" section of the wiki.

System overview (for context, don't repeat):
{system_narrative[:500]}

{subsection_guide}

Source code context:
{source_context[:40000]}

{f"Additional analysis findings:{chr(10)}{dossier_context}" if dossier_context else ""}

IMPORTANT FORMATTING RULES:
1. Reference code entities using [[entity:qualified.name]] markers. You MUST reference at least 60% of the entities listed below. Examples:
   - "The [[entity:server.AirlineServer]] class initializes the application..."
   - "This calls [[entity:agents.triage.run_triage]] to determine the best agent"
   - "The [[entity:models.Flight]] dataclass stores flight details"
   - "Error handling is done via [[entity:utils.exceptions.handle_error]]"
   - "Configuration is loaded by [[entity:config.Settings.from_env]]"
2. Reference other sections using [[section:section-slug]] markers. Examples:
   - "See [[section:agent-orchestration]] for details"
3. Request inline code blocks using [[code:filepath:start_line:end_line]] markers. Examples:
   - "The configuration is defined as: [[code:server.py:12:25]]"
4. Use ## for subsection headings, ### for sub-subsections
5. Write PROFESSIONAL PROSE that explains WHY, not just WHAT
6. Include specific details from the source code — function names, class names, patterns
7. DO NOT use markdown code fences (```). Use [[code:...]] markers instead
{entity_list_text}

Other sections you can cross-reference:
{chr(10).join(other_sections)}

Write the section content now."""

    try:
        prose = chat(
            [{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.3,
            cache_ttl=3600,
        )
    except Exception as exc:
        logger.error("Section narration failed for %s: %s", section.title, exc)
        prose = f"Documentation for {section.title} is being generated."

    prose = prose.strip()

    # Strip leading "# Title" if it matches the section title (Gap 6)
    prose = _strip_leading_title(prose, section.title)

    # Inject cross-section links for other section titles mentioned in prose
    prose = _inject_cross_section_links(prose, section.id, plan.sections)

    # Inject missing entity markers if too few were referenced (Gap 2)
    if section_entity_names:
        prose = _inject_missing_entity_markers(prose, section_entity_names)

    # Extract referenced entities from markers
    entity_refs = re.findall(r"\[\[entity:([^\]]+)\]\]", prose)
    section_refs = re.findall(r"\[\[section:([^\]]+)\]\]", prose)
    code_refs = [
        {"file_path": m[0], "start_line": int(m[1]), "end_line": int(m[2])}
        for m in re.findall(r"\[\[code:([^:]+):(\d+):(\d+)\]\]", prose)
    ]

    # Extract subsection headings from the prose (## through ####)
    subsections = []
    for match in re.finditer(r"^(#{2,4})\s+(.+)$", prose, re.MULTILINE):
        title = match.group(2).strip()
        sub_id = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        subsections.append({"id": sub_id, "title": title})

    # Convert ## / ### / #### headings to [[heading:level:Title]] markers
    def _heading_replacer(m: re.Match) -> str:
        level = len(m.group(1))
        title = m.group(2).strip()
        return f"[[heading:{level}:{title}]]"

    prose = re.sub(r"^(#{2,4})\s+(.+)$", _heading_replacer, prose, flags=re.MULTILINE)

    return NarratedSection(
        section_id=section.id,
        title=section.title,
        prose=prose,
        entities_referenced=entity_refs,
        sections_referenced=section_refs,
        code_blocks=code_refs,
        tables=[],  # tables generated by enricher, not narrator
        subsections=subsections,
    )


def generate_all_sections(
    plan: WikiPlan,
    system_narrative: str,
    compressed: CompressedCodebase,
    repo_path: str,
    entities: list[ParsedEntity],
    dossier=None,
) -> list[NarratedSection]:
    """Generate content for all sections in parallel."""
    results: list[NarratedSection] = []

    with ThreadPoolExecutor(max_workers=1) as pool:
        futures = {
            pool.submit(
                generate_section_content,
                section, system_narrative, compressed,
                plan, repo_path, entities, dossier,
            ): section
            for section in plan.sections
        }

        for future in as_completed(futures):
            section = futures[future]
            try:
                result = future.result(timeout=120)
                results.append(result)
                logger.info("Narrated section: %s", section.title)
            except Exception as exc:
                logger.error("Section %s failed: %s", section.title, exc)
                # Create empty section so the pipeline continues
                results.append(NarratedSection(
                    section_id=section.id,
                    title=section.title,
                    prose=f"Documentation for {section.title} could not be generated.",
                ))

    # Sort to match plan order
    plan_order = {s.id: i for i, s in enumerate(plan.sections)}
    results.sort(key=lambda r: plan_order.get(r.section_id, 999))

    return results


def _build_source_context(
    section: WikiSectionPlan,
    repo_path: str,
    entities: list[ParsedEntity],
    compressed: CompressedCodebase,
    max_chars: int = 50000,
) -> str:
    """Build source context for the LLM, tiered by file size.

    - <200 lines: include full file content
    - 200-1000 lines: include top entities (full body) + file summary
    - >1000 lines: include entity signatures + docstrings + file summary only
    """
    relevant_files = section.all_relevant_files
    relevant_entities = set(section.all_relevant_entities)

    # Index entities by file
    file_entities: dict[str, list[ParsedEntity]] = {}
    for e in entities:
        if e.file_path in relevant_files or e.qualified_name in relevant_entities:
            file_entities.setdefault(e.file_path, []).append(e)

    # If no files specified, use entities to find files
    if not relevant_files:
        relevant_files = sorted(file_entities.keys())

    parts: list[str] = []
    chars_used = 0

    for fp in relevant_files:
        if chars_used >= max_chars:
            break

        full_path = Path(repo_path) / fp
        file_ents = file_entities.get(fp, [])
        fs = compressed.file_summaries.get(fp)

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
            # Full file content
            content = "\n".join(lines)
            if len(content) > budget:
                content = content[:budget]
            part = f"\n--- {fp} (full file, {line_count} lines) ---\n{content}"
        elif line_count < 1000:
            # Top entities + file summary
            part_lines = [f"\n--- {fp} ({line_count} lines) ---"]
            if fs:
                part_lines.append(f"Summary: {fs.summary}")
            for e in file_ents[:10]:
                if e.line_start and e.line_end and lines:
                    body = "\n".join(lines[max(0, e.line_start - 1):min(e.line_end, len(lines))])
                    if len(body) < 2000:
                        part_lines.append(f"\n{e.entity_type} {e.qualified_name}:\n{body}")
                    else:
                        part_lines.append(
                            f"\n{e.entity_type} {e.qualified_name}: {e.signature or e.name}"
                        )
            part = "\n".join(part_lines)
        else:
            # Signatures + docstrings only
            part_lines = [f"\n--- {fp} ({line_count} lines, large file) ---"]
            if fs:
                part_lines.append(f"Summary: {fs.summary}")
            for e in file_ents[:15]:
                sig = e.signature or e.name
                doc = f" — {e.docstring[:100]}" if e.docstring else ""
                part_lines.append(f"  {e.entity_type} {e.qualified_name}: {sig}{doc}")
            part = "\n".join(part_lines)

        if len(part) > budget:
            part = part[:budget]

        parts.append(part)
        chars_used += len(part)

    return "\n".join(parts)


def _get_dossier_context(section: WikiSectionPlan, dossier) -> str:
    """Extract relevant dossier findings for a section."""
    parts: list[str] = []

    # Security findings relevant to section files
    relevant_files = set(section.all_relevant_files)
    if dossier.security:
        for finding in dossier.security[:5]:
            if relevant_files & set(finding.related_files):
                parts.append(
                    f"Security ({finding.severity.value}): {finding.description}"
                )

    # Architecture info
    arch = dossier.sections.get("architecture")
    if arch:
        parts.append(
            f"Architecture: {arch.primary_style}, "
            f"patterns: {', '.join(arch.patterns_detected[:3])}"
        )

    # Technical debt
    tech_debt = dossier.sections.get("technical_debt")
    if tech_debt:
        relevant_debt = [
            item for item in tech_debt.items
            if item.file_path in relevant_files
        ]
        if relevant_debt:
            parts.append(
                f"Technical debt: {len(relevant_debt)} items in these files"
            )

    return "\n".join(parts)


def _strip_leading_title(prose: str, section_title: str) -> str:
    """Strip leading '# Title' if it matches the section title."""
    lines = prose.split("\n", 1)
    first = lines[0].strip()
    if first.startswith("#"):
        heading_text = first.lstrip("#").strip()
        if _titles_match(heading_text, section_title):
            return lines[1].lstrip("\n") if len(lines) > 1 else ""
    return prose


def _titles_match(a: str, b: str) -> bool:
    """Fuzzy title comparison — case-insensitive, ignore punctuation."""
    def normalize(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower())
    return normalize(a) == normalize(b)


def _inject_cross_section_links(
    prose: str,
    current_section_id: str,
    all_sections: list[WikiSectionPlan],
) -> str:
    """Replace first mention of other section titles with [[section:slug]] markers.

    Case-insensitive scan; only replaces if not already inside a [[...]] marker.
    """
    for section in all_sections:
        if section.id == current_section_id:
            continue
        # Skip if already has a marker for this section
        if f"[[section:{section.id}]]" in prose:
            continue
        # Case-insensitive first-occurrence replacement
        pattern = re.compile(r"\b" + re.escape(section.title) + r"\b", re.IGNORECASE)
        match = pattern.search(prose)
        if match:
            # Don't replace if inside an existing marker
            before = prose[:match.start()]
            if "[[" in before and before.rindex("[[") > before.rfind("]]"):
                continue
            prose = prose[:match.start()] + f"[[section:{section.id}]]" + prose[match.end():]
    return prose


def _inject_missing_entity_markers(
    prose: str,
    section_entities: list[str],
) -> str:
    """Append a 'Key Components' paragraph referencing unreferenced entities."""
    referenced = set(re.findall(r"\[\[entity:([^\]]+)\]\]", prose))
    unreferenced = [
        qn for qn in section_entities
        if qn not in referenced
    ]

    if not unreferenced:
        return prose

    # Only inject if >40% unreferenced
    coverage = len(referenced) / max(len(section_entities), 1)
    if coverage >= 0.4:
        return prose

    # Append a brief paragraph with the unreferenced entities
    markers = ", ".join(
        f"[[entity:{qn}]]" for qn in unreferenced[:50]
    )
    prose += f"\n\n### Key Components\n\nThis section also involves {markers}."
    return prose
