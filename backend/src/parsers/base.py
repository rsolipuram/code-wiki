"""Abstract base class for all language-specific code parsers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedEntity:
    """A code entity extracted by a parser."""

    name: str
    qualified_name: str
    entity_type: str  # function | method | class | module | interface | variable
    file_path: str
    line_start: int
    line_end: int
    signature: Optional[str] = None
    docstring: Optional[str] = None
    # dotted qualified names of entities this one calls
    calls: list[str] = field(default_factory=list)
    # dotted qualified names of modules/files imported
    imports: list[str] = field(default_factory=list)
    # raw extra data (decorators, return type, parameters list, etc.)
    entity_metadata: dict = field(default_factory=dict)


@dataclass
class Dependency:
    """A resolved import/require statement."""

    source_file: str  # file that contains the import
    imported_name: str  # qualified name being imported
    resolved_path: Optional[str] = None  # absolute path if resolvable


@dataclass
class CallEdge:
    """A directed call relationship between two qualified names."""

    caller: str  # qualified name of the calling entity
    callee: str  # qualified name of the called entity


class CodeParser(ABC):
    """Language-agnostic interface for code structure extraction.

    All language-specific parsers MUST implement this interface so the rest of
    the system can remain parser-agnostic (per Constitution Principle III).
    """

    @abstractmethod
    def parse_file(self, file_path: str, repo_path: str = "") -> list[ParsedEntity]:
        """Parse a single source file and return all extracted entities.

        Args:
            file_path: Absolute path to the source file.
            repo_path: Absolute path to the repository root.
        """

    @abstractmethod
    def resolve_imports(self, file_path: str, repo_path: str = "") -> list[Dependency]:
        """Resolve all import statements in a file to their targets.

        Args:
            file_path: Absolute path to the source file.
            repo_path: Absolute path to the repository root.
        """

    @abstractmethod
    def get_call_graph(self, file_path: str, repo_path: str = "") -> list[CallEdge]:
        """Extract caller→callee pairs from a single file.

        Args:
            file_path: Absolute path to the source file.
            repo_path: Absolute path to the repository root.
        """


class UnsupportedLanguageError(Exception):
    """Raised when no parser is registered for a file extension."""
