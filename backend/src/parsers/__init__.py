"""Parser registry mapping file extensions to language-specific parsers.

Usage:
    from src.parsers import get_parser
    parser = get_parser(".py")
    entities = parser.parse_file("/path/to/file.py")
"""

from src.parsers.base import CodeParser, UnsupportedLanguageError
from src.parsers.python_parser import PythonParser
from src.parsers.rust_parser import RustParser
from src.parsers.typescript_parser import SUPPORTED_EXTENSIONS as _TS_EXTS
from src.parsers.typescript_parser import TypeScriptParser

_PYTHON_PARSER: PythonParser | None = None
_TS_PARSER: TypeScriptParser | None = None
_RUST_PARSER: RustParser | None = None

_EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".rs": "rust",
    **{ext: "typescript" for ext in _TS_EXTS},
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
    global _PYTHON_PARSER, _TS_PARSER, _RUST_PARSER

    lang = _EXTENSION_MAP.get(extension.lower())
    if lang == "python":
        if _PYTHON_PARSER is None:
            _PYTHON_PARSER = PythonParser()
        return _PYTHON_PARSER
    if lang == "typescript":
        if _TS_PARSER is None:
            _TS_PARSER = TypeScriptParser()
        return _TS_PARSER
    if lang == "rust":
        if _RUST_PARSER is None:
            _RUST_PARSER = RustParser()
        return _RUST_PARSER

    raise UnsupportedLanguageError(
        f"No parser registered for extension {extension!r}. "
        f"Supported: {sorted(_EXTENSION_MAP)}"
    )


def supported_extensions() -> list[str]:
    """Return all file extensions that have a registered parser."""
    return sorted(_EXTENSION_MAP.keys())
