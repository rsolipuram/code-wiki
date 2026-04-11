"""Entity extraction pipeline.

Walks a repository directory, parses each supported file, and produces
CodeEntity records for PostgreSQL + Ladybug-backed graph persistence.
"""

import logging
from pathlib import Path

from src.parsers import get_parser, supported_extensions
from src.parsers.base import ParsedEntity, UnsupportedLanguageError

logger = logging.getLogger(__name__)

# Directories to always skip during extraction
_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", "out", ".next", ".nuxt", "coverage", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "target", "vendor", ".gradle",
}


def extract_entities(
    repo_path: str,
    extensions: list[str] | None = None,
    build_output_dirs: tuple[str, ...] | list[str] = (),
) -> list[ParsedEntity]:
    """Walk a repository and extract all code entities from supported files.

    Args:
        repo_path: Absolute path to the repository root.
        extensions: Optional list of extensions to include (e.g. [".py", ".ts"]).
                    Defaults to all supported extensions.
        build_output_dirs: Directories to skip (build outputs, minified bundles).

    Returns:
        Flat list of ParsedEntity objects from all parsed files.
    """
    root = Path(repo_path)
    if not root.exists():
        raise FileNotFoundError(f"Repository path does not exist: {repo_path}")

    allowed_exts = set(extensions or supported_extensions())
    build_dirs = set(build_output_dirs)
    all_entities: list[ParsedEntity] = []
    parsed_files = 0
    skipped_files = 0
    artifact_skips = 0

    lang_stats: dict[str, int] = {}

    for file_path in _walk_repo(root, allowed_exts, build_dirs):
        if _is_build_artifact(file_path):
            artifact_skips += 1
            logger.debug("Skipped build artifact: %s", file_path)
            continue

        ext = file_path.suffix.lower()
        try:
            parser = get_parser(ext)
        except UnsupportedLanguageError:
            skipped_files += 1
            continue

        try:
            logger.debug("Parsing: %s", file_path)
            entities = parser.parse_file(str(file_path), str(root))
            all_entities.extend(entities)
            parsed_files += 1
            lang_stats[ext] = lang_stats.get(ext, 0) + 1
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", file_path, exc)
            skipped_files += 1

    # Log per-language stats breakdown
    stats_parts = [f"{ext}: {count}" for ext, count in sorted(lang_stats.items())]
    logger.info(
        "Extraction complete: %d files parsed, %d skipped, %d artifacts filtered, %d entities found | %s",
        parsed_files,
        skipped_files,
        artifact_skips,
        len(all_entities),
        ", ".join(stats_parts) if stats_parts else "no files",
    )
    return all_entities


_MINIFIED_EXTENSIONS = {".js", ".cjs", ".mjs"}


def _is_build_artifact(file_path: Path) -> bool:
    """Detect minified/bundled files that should be excluded from analysis."""
    if file_path.suffix.lower() not in _MINIFIED_EXTENSIONS:
        return False

    try:
        chunk = file_path.read_bytes()[:4096]
        lines = chunk.split(b"\n")
        # Single-line bundles > 10KB
        if len(lines) <= 2 and file_path.stat().st_size > 10240:
            return True
        # High average line length indicates minification
        if lines:
            avg_len = len(chunk) / max(len(lines), 1)
            if avg_len > 300:
                return True
    except OSError:
        pass

    return False


def _walk_repo(
    root: Path,
    allowed_exts: set[str],
    build_dirs: set[str] | None = None,
):
    """Yield all files under root matching allowed_exts, skipping ignored dirs."""
    skip = _SKIP_DIRS | (build_dirs or set())
    for item in root.rglob("*"):
        if any(part in skip for part in item.parts):
            continue
        if item.is_file() and item.suffix.lower() in allowed_exts:
            yield item
