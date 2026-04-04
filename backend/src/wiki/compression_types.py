"""V2 wiki pipeline data structures.

Defines all typed containers flowing through the 5-phase pipeline:
  Phase 0 (Compress) → CompressedCodebase
  Phase 1 (Plan)     → WikiPlan
  Phase 2 (Narrate)  → NarratedSection
  Phase 3 (Enrich)   → EnrichedSection
  Phase 4 (Render)   → dict (V2 content schema)
"""

from dataclasses import dataclass, field


@dataclass
class FileSummary:
    file_path: str
    language: str
    line_count: int
    summary: str  # ~50 words from LLM, or empty for "none" compression
    entity_count: int
    key_entities: list[str] = field(default_factory=list)  # qualified names
    exported_symbols: list[str] = field(default_factory=list)  # e.g. ["triage_agent", "cancel_flight"]
    dependencies: list[str] = field(default_factory=list)    # e.g. ["openai", "db_utils"]
    nav_topic: str = ""   # wiki section this file belongs to (e.g. "Agent Architecture")
    nav_role: str = ""    # "primary" | "supporting" | "config" | "test"


@dataclass
class DirectorySummary:
    dir_path: str
    file_count: int
    summary: str  # ~100 words
    child_files: list[str] = field(default_factory=list)
    key_entities: list[str] = field(default_factory=list)
    nav_items: list[dict] = field(default_factory=list)  # [{section, subsections, importance, seed_files}]


@dataclass
class CompressedCodebase:
    repo_summary: str  # ~500 words, whole-repo overview
    file_summaries: dict[str, FileSummary] = field(default_factory=dict)
    directory_summaries: dict[str, DirectorySummary] = field(default_factory=dict)
    key_entities: list[dict] = field(default_factory=list)  # top-50 entities
    call_graph_summary: str = ""  # "A calls B, B calls C"
    import_graph_summary: str = ""  # "module X imports Y"
    compression_level: str = "none"  # "none" | "file_only" | "full_pyramid"
    nav_plan: dict = field(default_factory=dict)  # consolidated navigation from compression


@dataclass
class WikiSubsection:
    id: str  # URL slug
    title: str
    relevant_files: list[str] = field(default_factory=list)
    relevant_entities: list[str] = field(default_factory=list)  # qualified names
    describes: str = ""  # what this subsection should explain


@dataclass
class WikiSectionPlan:
    id: str  # URL slug
    title: str
    subsections: list[WikiSubsection] = field(default_factory=list)
    diagram_type: str = "none"  # "flowchart" | "sequence" | "architecture" | "none"
    table_type: str = "none"  # "components" | "apis" | "tools" | "none"

    @property
    def all_relevant_files(self) -> list[str]:
        """Collect all relevant files from subsections."""
        seen: set[str] = set()
        result: list[str] = []
        for sub in self.subsections:
            for f in sub.relevant_files:
                if f not in seen:
                    seen.add(f)
                    result.append(f)
        return result

    @property
    def all_relevant_entities(self) -> list[str]:
        """Collect all relevant entities from subsections."""
        seen: set[str] = set()
        result: list[str] = []
        for sub in self.subsections:
            for e in sub.relevant_entities:
                if e not in seen:
                    seen.add(e)
                    result.append(e)
        return result


@dataclass
class WikiPlan:
    title: str
    sections: list[WikiSectionPlan] = field(default_factory=list)
    total_files_covered: int = 0
    uncovered_files: list[str] = field(default_factory=list)


@dataclass
class NarratedSection:
    section_id: str
    title: str
    prose: str  # Raw prose with [[entity:X]] [[section:Y]] [[code:F:S:E]] markers
    entities_referenced: list[str] = field(default_factory=list)
    sections_referenced: list[str] = field(default_factory=list)
    code_blocks: list[dict] = field(default_factory=list)  # [{file_path, start_line, end_line}]
    tables: list[dict] = field(default_factory=list)  # [{headers, rows}]
    subsections: list[dict] = field(default_factory=list)  # [{id, title}]


@dataclass
class EnrichedSection:
    section_id: str
    title: str
    prose_segments: list[dict] = field(default_factory=list)
    diagrams: list[dict] = field(default_factory=list)  # [{mermaid_source, caption}]
    tables: list[dict] = field(default_factory=list)  # [{headers, rows}]
    source_links: list[dict] = field(default_factory=list)  # [{entity_name, qualified_name, url, line}]
    code_blocks: list[dict] = field(default_factory=list)  # [{language, code, file_path, start_line}]
    subsections: list[dict] = field(default_factory=list)  # [{id, title, anchor}]
    word_count: int = 0
    key_components: list[dict] = field(default_factory=list)  # [{name, type, qualified_name, file_path}]
    internal_deps: list[str] = field(default_factory=list)  # directory paths of cross-section deps
    related_pages: list[dict] = field(default_factory=list)  # [{slug, title}]
