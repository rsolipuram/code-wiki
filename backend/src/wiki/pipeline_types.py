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
        digits = []
        started = False
        for ch in s:
            if ch.isdigit() or (ch == "-" and not started):
                digits.append(ch)
                started = True
            elif started:
                break
        if not digits or digits == ["-"]:
            return default
        return int("".join(digits))
    except Exception:
        return default


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

    sub_group: str = ""
    # Optional secondary grouping for 3-level nesting: menu_group > sub_group > menu_label

    key_insights: list[str] = field(default_factory=list)
    # Critical architectural / logic-flow insights the writer MUST cover.
    # e.g. ["All requests route through triage_agent before reaching specialists",
    #        "Context is rebuilt from memory_store on every turn"]

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
            "sub_group": self.sub_group,
            "key_insights": self.key_insights,
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
            sub_group=d.get("sub_group", ""),
            key_insights=d.get("key_insights", []),
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


# ── Planner-internal grouping model ───────────────────────────────────────────

@dataclass
class MenuGroupPlan:
    """Planner phase-A output: one navigation group and its scoped directories."""

    group_name: str
    scope_dirs: list[str] = field(default_factory=list)
    expected_sections: int = 2
    boundary_hint: str = ""
    importance: str = "supporting"  # "core" | "supporting" | "peripheral"

    def to_dict(self) -> dict:
        return {
            "group_name": self.group_name,
            "scope_dirs": self.scope_dirs,
            "expected_sections": self.expected_sections,
            "boundary_hint": self.boundary_hint,
            "importance": self.importance,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MenuGroupPlan":
        return cls(
            group_name=d.get("group_name", ""),
            scope_dirs=d.get("scope_dirs", []) or [],
            expected_sections=_safe_int(d.get("expected_sections", 2), default=2),
            boundary_hint=d.get("boundary_hint", "") or "",
            importance=d.get("importance", "supporting") or "supporting",
        )


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
