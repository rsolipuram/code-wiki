"""Parser registry mapping file extensions to Tree-sitter parsers.

Usage:
    from src.parsers import get_parser
    parser = get_parser(".py")
    entities = parser.parse_file("/path/to/file.py")
"""

from src.parsers.base import CodeParser, UnsupportedLanguageError
from src.parsers.tree_sitter_parser import TreeSitterParser

_PARSERS: dict[str, TreeSitterParser] = {}

_EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".cs": "csharp",
    ".java": "java",
    ".rs": "rust",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "typescript",
    ".jsx": "tsx",
    ".mjs": "typescript",
    ".cjs": "typescript",
}


def get_parser(extension: str) -> CodeParser:
    """Return the appropriate CodeParser for the given file extension.

    Args:
        extension: File extension including the dot, e.g. ".py", ".ts".

    Returns:
        A CodeParser instance (shared singleton per language).

    Raises:
        UnsupportedLanguageError: If no parser is registered for the extension.
    """
    lang = _EXTENSION_MAP.get(extension.lower())
    if lang:
        parser = _PARSERS.get(lang)
        if parser is None:
            parser = TreeSitterParser(lang)
            _PARSERS[lang] = parser
        return parser

    raise UnsupportedLanguageError(
        f"No parser registered for extension {extension!r}. "
        f"Supported: {sorted(_EXTENSION_MAP)}"
    )


def supported_extensions() -> list[str]:
    """Return all file extensions that have a registered parser."""
    return sorted(_EXTENSION_MAP.keys())
