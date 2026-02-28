"""RepoFingerprint dataclass — output of the Layer 0 Repo Reconnaissance agent."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class RepoFingerprint:
    """Immutable snapshot of a repository's structural characteristics.

    Produced by RepoRecon (zero LLM calls) and consumed by the Triage Agent
    and all Layer 1 facet agents.
    """

    # Language detection
    languages: list[str] = field(default_factory=list)
    primary_language: Optional[str] = None

    # System classification (monolith | microservices | library | cli | unknown)
    system_type: str = "unknown"

    # Tools / frameworks detected
    tools_present: list[str] = field(default_factory=list)

    # Size metrics
    file_count: int = 0
    loc: int = 0  # lines of code (excluding blanks and comments)

    # Config file map: {config_type: [file_paths]}
    config_files: dict[str, list[str]] = field(default_factory=dict)

    # Project identity (from package manifests)
    project_name: str = ""
    project_description: str = ""

    # Source layout
    source_roots: tuple[str, ...] = ()
    build_output_dirs: tuple[str, ...] = ()
    entry_points: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary (JSON-compatible)."""
        return {
            "languages": list(self.languages),
            "primary_language": self.primary_language,
            "system_type": self.system_type,
            "tools_present": list(self.tools_present),
            "file_count": self.file_count,
            "loc": self.loc,
            "config_files": {k: list(v) for k, v in self.config_files.items()},
            "project_name": self.project_name,
            "project_description": self.project_description,
            "source_roots": list(self.source_roots),
            "build_output_dirs": list(self.build_output_dirs),
            "entry_points": list(self.entry_points),
        }
