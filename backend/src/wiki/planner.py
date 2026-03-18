"""Phase 1: Feature-based document planning.

Uses a single LLM call to organize wiki content by features/concerns
rather than directory structure. Falls back to directory-based plan
if the LLM produces invalid JSON.
"""

import json
import logging
import re
from typing import Optional

from src.llm.client import chat
from src.recon.fingerprint import RepoFingerprint
from src.wiki.page_builders.module_page import slugify
from src.wiki.v2_types import (
    CompressedCodebase,
    WikiPlan,
    WikiSectionPlan,
    WikiSubsection,
)

logger = logging.getLogger(__name__)


def plan_wiki(
    compressed: CompressedCodebase,
    fingerprint: RepoFingerprint,
    dossier=None,
) -> WikiPlan:
    """Plan wiki structure using an LLM call.

    Organizes content by feature/concern, not directory.
    Falls back to directory-based plan on failure.
    """
    # Build prompt context
    dir_summaries_text = ""
    if compressed.directory_summaries:
        lines = []
        for dp, ds in sorted(compressed.directory_summaries.items()):
            lines.append(f"  - {dp}/ ({ds.file_count} files): {ds.summary}")
        dir_summaries_text = "\n".join(lines)

    key_entities_text = ""
    if compressed.key_entities:
        lines = []
        for e in compressed.key_entities[:30]:
            lines.append(
                f"  - {e['entity_type']} {e['qualified_name']}: "
                f"{e.get('docstring', '')[:80] or e.get('signature', '')[:80]}"
            )
        key_entities_text = "\n".join(lines)

    # Collect all file paths from file_summaries
    all_files = sorted(compressed.file_summaries.keys()) if compressed.file_summaries else []

    prompt = f"""You are a technical writer planning a code wiki. Organize the documentation by FEATURES and CONCERNS, not by directory structure.

Repository: {fingerprint.project_name or 'unknown'}
Description: {compressed.repo_summary[:500]}
Files: {fingerprint.file_count}, LOC: {fingerprint.loc}

{f"Directory summaries:{chr(10)}{dir_summaries_text}" if dir_summaries_text else ""}

{f"Key entities:{chr(10)}{key_entities_text}" if key_entities_text else ""}

{f"Call graph: {compressed.call_graph_summary[:500]}" if compressed.call_graph_summary else ""}

Output a JSON object with this exact structure:
{{
  "title": "Project Name Documentation",
  "sections": [
    {{
      "id": "url-slug",
      "title": "Section Title",
      "subsections": [
        {{
          "id": "sub-slug",
          "title": "Subsection Title",
          "relevant_files": ["path/to/file.py"],
          "relevant_entities": ["qualified.name"],
          "describes": "What this subsection explains"
        }}
      ],
      "diagram_type": "architecture",
      "table_type": "components"
    }}
  ]
}}

Rules:
- Maximum 8 sections, maximum 5 subsections per section
- Every source file must appear in at least one subsection's relevant_files
- diagram_type: "architecture", "flowchart", "sequence", or "none"
- table_type: "components", "apis", "tools", or "none"
- Section IDs must be URL-safe slugs (lowercase, hyphens)
- Focus on WHAT the code does, not WHERE files are located
- Group related functionality across directories into single sections

Output ONLY valid JSON, no markdown fences or explanation."""

    for attempt in range(3):
        try:
            response = chat(
                [{"role": "user", "content": prompt}],
                max_tokens=4096,
                temperature=0.2 + (attempt * 0.2),
                cache_ttl=3600 if attempt == 0 else 0,
            )

            # Strip markdown fences if present
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```\w*\n?", "", cleaned)
                cleaned = re.sub(r"\n?```$", "", cleaned)

            # Repair common LLM JSON issues
            cleaned = _repair_json(cleaned)

            data = json.loads(cleaned)
            plan = _parse_plan(data)

            if plan.sections:
                logger.info(
                    "Wiki plan: %d sections, title=%s",
                    len(plan.sections), plan.title,
                )
                return plan

        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning(
                "Plan JSON parse failed (attempt %d/3): %s", attempt + 1, exc,
            )

    logger.warning("Plan LLM failed after retries, using fallback")
    return _fallback_plan(fingerprint, compressed)


def _parse_plan(data: dict) -> WikiPlan:
    """Parse raw JSON dict into WikiPlan."""
    sections = []
    for s in data.get("sections", []):
        subsections = []
        for sub in s.get("subsections", []):
            subsections.append(WikiSubsection(
                id=sub.get("id", slugify(sub.get("title", "unknown"))),
                title=sub.get("title", ""),
                relevant_files=sub.get("relevant_files", []),
                relevant_entities=sub.get("relevant_entities", []),
                describes=sub.get("describes", ""),
            ))
        sections.append(WikiSectionPlan(
            id=s.get("id", slugify(s.get("title", "unknown"))),
            title=s.get("title", ""),
            subsections=subsections,
            diagram_type=s.get("diagram_type", "none"),
            table_type=s.get("table_type", "none"),
        ))
    return WikiPlan(
        title=data.get("title", "Documentation"),
        sections=sections,
    )


def _repair_json(text: str) -> str:
    """Fix common LLM JSON issues: trailing commas, unquoted keys, etc."""
    # Remove trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)
    # Remove single-line // comments
    text = re.sub(r"//[^\n]*", "", text)
    return text.strip()


def _fallback_plan(
    fingerprint: RepoFingerprint,
    compressed: CompressedCodebase,
) -> WikiPlan:
    """Build a directory-based plan from compressed data.

    Used when LLM planning fails. File paths are normalized to match
    the entity_index (repo-relative, not cache-absolute).
    """
    from pathlib import Path

    # Find and strip the cache repo prefix if present (e.g. "cache/repos/https___.../")
    # by detecting the common prefix of all file paths
    def _strip_cache_prefix(fp: str) -> str:
        """Normalize file paths to repo-relative (match entity_index convention)."""
        # Detect cache/repos/ prefix pattern
        idx = fp.find("/cache/repos/")
        if idx >= 0:
            # Find the next directory after the repo slug
            after_cache = fp[idx + len("/cache/repos/"):]
            # The repo slug is the first path component (e.g. "https___github_com_...")
            parts = after_cache.split("/", 1)
            if len(parts) > 1:
                return parts[1]
        # Also handle relative cache/repos/ prefix
        if fp.startswith("cache/repos/"):
            after = fp[len("cache/repos/"):]
            parts = after.split("/", 1)
            if len(parts) > 1:
                return parts[1]
        return fp

    def _normalize_files(files: list[str]) -> list[str]:
        return [_strip_cache_prefix(f) for f in files]

    def _clean_title(dir_path: str) -> str:
        """Create a clean section title from a directory path."""
        cleaned = _strip_cache_prefix(dir_path)
        return cleaned.replace("/", " / ").title()

    sections: list[WikiSectionPlan] = []

    if compressed.directory_summaries:
        # Group by top-level directory
        for dir_path, ds in sorted(compressed.directory_summaries.items()):
            clean_dir = _strip_cache_prefix(dir_path)
            section_id = slugify(clean_dir.replace("/", "-"))
            title = _clean_title(dir_path)
            child_files = _normalize_files(ds.child_files)
            sections.append(WikiSectionPlan(
                id=section_id,
                title=title,
                subsections=[WikiSubsection(
                    id=f"{section_id}-overview",
                    title=f"{title} Overview",
                    relevant_files=child_files,
                    relevant_entities=ds.key_entities,
                    describes=ds.summary,
                )],
                diagram_type="architecture" if len(child_files) > 3 else "none",
                table_type="components",
            ))
    elif compressed.file_summaries:
        # Group files by parent directory
        dir_groups: dict[str, list[str]] = {}
        for fp in compressed.file_summaries:
            clean = _strip_cache_prefix(fp)
            parent = str(Path(clean).parent)
            dir_groups.setdefault(parent, []).append(clean)

        for dir_path, files in sorted(dir_groups.items()):
            section_id = slugify(dir_path.replace("/", "-")) or "root"
            title = dir_path.replace("/", " / ").title() if dir_path != "." else "Root"
            key_ents = []
            for fp in files:
                # Try both original and prefixed versions for lookup
                fs = compressed.file_summaries.get(fp)
                if fs:
                    key_ents.extend(fs.key_entities)

            sections.append(WikiSectionPlan(
                id=section_id,
                title=title,
                subsections=[WikiSubsection(
                    id=f"{section_id}-overview",
                    title=f"{title} Overview",
                    relevant_files=files,
                    relevant_entities=key_ents[:10],
                    describes=f"Files in {dir_path}",
                )],
                diagram_type="architecture" if len(files) >= 3 else "none",
                table_type="components",
            ))
    else:
        # Minimal fallback — single section
        sections.append(WikiSectionPlan(
            id="overview",
            title="Project Overview",
            subsections=[WikiSubsection(
                id="overview-main",
                title="Overview",
                describes="Complete project overview",
            )],
            diagram_type="none",
            table_type="components",
        ))

    return WikiPlan(
        title=f"{fingerprint.project_name or 'Project'} Documentation",
        sections=sections[:8],  # max 8
    )


def validate_coverage(
    plan: WikiPlan,
    all_files: list[str],
) -> list[str]:
    """Check which files aren't covered by any subsection.

    Returns list of uncovered file paths.
    """
    covered: set[str] = set()
    for section in plan.sections:
        for sub in section.subsections:
            covered.update(sub.relevant_files)

    uncovered = [f for f in all_files if f not in covered]
    plan.total_files_covered = len(all_files) - len(uncovered)

    if uncovered:
        logger.warning(
            "Plan coverage: %d/%d files uncovered",
            len(uncovered), len(all_files),
        )
        plan.uncovered_files = uncovered

    return uncovered
