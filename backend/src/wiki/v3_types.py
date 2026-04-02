"""V3 wiki pipeline data structures.

Defines typed containers flowing through the V3 two-phase pipeline:
  Phase 1 (Plan)    → WikiNav (content planner output)
  Phase 2 (Write)   → V3Section (deep content agent output, per section)
  Phase 3 (Assemble) → assembled prose_segments[]
  Phase 4 (Resolve)  → cross-refs resolved
"""

from dataclasses import dataclass, field
from operator import add
from typing import Annotated, Optional, TypedDict


# ── Content Planner output ────────────────────────────────────────────────────

@dataclass
class SectionSpec:
    """Single section entry from Content Planner output."""

    slug: str
    title: str
    type: str = "concept"
    # "concept" | "architecture" | "workflow" | "reference" | "home"

    one_liner: str = ""
    # One-sentence description for sidebar/TOC

    focus_tags: list[str] = field(default_factory=list)
    # Dossier tags the agent should pull findings from
    # e.g. ["architecture", "dependencies", "security"]

    seed_files: list[str] = field(default_factory=list)
    # Relative file paths to start exploration from (agent can read others)

    boundary_hint: str = ""
    # Natural language hint about scope: e.g. "Focus on auth flow, not persistence"

    cross_refs: list[str] = field(default_factory=list)
    # Section slugs this section is likely to reference

    menu_group: str = ""
    # Optional sidebar group label for submenu rendering

    menu_label: str = ""
    # Optional child label shown inside menu_group

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "title": self.title,
            "type": self.type,
            "one_liner": self.one_liner,
            "focus_tags": self.focus_tags,
            "seed_files": self.seed_files,
            "boundary_hint": self.boundary_hint,
            "cross_refs": self.cross_refs,
            "menu_group": self.menu_group,
            "menu_label": self.menu_label,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SectionSpec":
        return cls(
            slug=d.get("slug", ""),
            title=d.get("title", ""),
            type=d.get("type", "concept"),
            one_liner=d.get("one_liner", ""),
            focus_tags=d.get("focus_tags", []),
            seed_files=d.get("seed_files", []),
            boundary_hint=d.get("boundary_hint", ""),
            cross_refs=d.get("cross_refs", []),
            menu_group=d.get("menu_group", ""),
            menu_label=d.get("menu_label", ""),
        )


@dataclass
class WikiNav:
    """Output of the Content Planner Agent — the ordered navigation structure."""

    title: str
    # e.g. "openai-cs-agents-demo — Documentation"

    sections: list[SectionSpec] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "sections": [s.to_dict() for s in self.sections],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WikiNav":
        return cls(
            title=d.get("title", "Documentation"),
            sections=[SectionSpec.from_dict(s) for s in d.get("sections", [])],
        )

    def slug_map(self) -> dict[str, str]:
        """Return {title: slug} mapping for cross-ref resolution."""
        return {s.title: s.slug for s in self.sections}


# ── Deep Content Agent output ─────────────────────────────────────────────────

@dataclass
class V3Section:
    """Output of a single Deep Content Agent run (per section)."""

    section_slug: str
    section_title: str

    raw_markdown: str = ""
    # Raw LLM output including special XML tags

    prose_segments: list[dict] = field(default_factory=list)
    # Assembled typed segments (populated by TagAssembler)

    word_count: int = 0
    critic_passed: bool = True
    critic_retries: int = 0

    is_reference_page: bool = False
    # True for Getting Started, Glossary, API Reference

    page_content: dict = field(default_factory=dict)
    # Optional pre-assembled page payload for structured special pages.

    def to_dict(self) -> dict:
        return {
            "section_slug": self.section_slug,
            "section_title": self.section_title,
            "raw_markdown": self.raw_markdown,
            "prose_segments": self.prose_segments,
            "word_count": self.word_count,
            "critic_passed": self.critic_passed,
            "critic_retries": self.critic_retries,
            "is_reference_page": self.is_reference_page,
            "page_content": self.page_content,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "V3Section":
        return cls(
            section_slug=d.get("section_slug", ""),
            section_title=d.get("section_title", ""),
            raw_markdown=d.get("raw_markdown", ""),
            prose_segments=d.get("prose_segments", []),
            word_count=d.get("word_count", 0),
            critic_passed=d.get("critic_passed", True),
            critic_retries=d.get("critic_retries", 0),
            is_reference_page=d.get("is_reference_page", False),
            page_content=d.get("page_content", {}),
        )


# ── LangGraph state ───────────────────────────────────────────────────────────

class V3WikiState(TypedDict, total=False):
    """LangGraph state flowing through the V3 wiki pipeline.

    Immutable inputs are set once at graph entry.
    Progressive outputs are updated by each node.
    """
    # ── Immutable inputs ──────────────────────────────────────────────────
    repo_path: str
    repo_url: str
    repo_name: str
    commit_hash: str
    repository_id: str

    dossier: dict               # Dossier.to_dict()
    compressed: dict            # CompressedCodebase as dict
    fingerprint: dict           # RepoFingerprint as dict
    entities: list              # ParsedEntity objects
    all_files: list             # relative str paths

    # ── Content Planner output ────────────────────────────────────────────
    wiki_nav: dict              # WikiNav.to_dict()

    # ── Per-section deep content (fan-out collects here) ─────────────────
    # Annotated[list, add] — each deep agent appends its V3Section dict
    deep_sections: Annotated[list, add]

    # ── Post-processing ───────────────────────────────────────────────────
    resolved_sections: list     # deep_sections with cross-refs resolved

    # ── Telemetry ─────────────────────────────────────────────────────────
    agent_results: Annotated[list, add]
