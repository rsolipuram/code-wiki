"""File system tools for V3 deep content agents.

All tools are read-only and close over repo_path via make_file_tools().
Agents call these to explore the codebase during wiki generation.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def make_file_tools(repo_path: str) -> list:
    """Create file system tools scoped to a specific repo.

    Args:
        repo_path: Absolute path to the cloned repository.

    Returns:
        List of LangChain tool functions.
    """
    _root = Path(repo_path).resolve()

    def _safe_path(rel: str) -> Optional[Path]:
        """Resolve path and ensure it stays inside repo_path."""
        try:
            resolved = (_root / rel).resolve()
            resolved.relative_to(_root)  # raises ValueError if outside
            return resolved
        except (ValueError, Exception):
            return None

    @tool
    def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        """Read source code from a file in the repository.

        Args:
            path: Relative file path within the repository (e.g. "src/auth/jwt.py").
            start_line: First line to read (1-indexed). None = beginning of file.
            end_line: Last line to read (1-indexed, inclusive). None = end of file.

        Returns:
            File contents with line numbers, or an error message.
        """
        full = _safe_path(path)
        if full is None:
            return f"Error: path {path!r} is outside the repository"
        if not full.exists():
            return f"File not found: {path}"
        if not full.is_file():
            return f"Not a file: {path}"

        try:
            lines = full.read_text(errors="replace").splitlines()
        except Exception as exc:
            return f"Error reading {path}: {exc}"

        total = len(lines)
        s = (start_line - 1) if start_line and start_line > 0 else 0
        e = end_line if end_line and end_line > 0 else total
        s = max(0, min(s, total))
        e = max(s, min(e, total))

        selected = lines[s:e]
        numbered = [f"{s + i + 1:5d} | {line}" for i, line in enumerate(selected)]
        header = f"# {path}  (lines {s+1}–{e} of {total})\n"
        return header + "\n".join(numbered)

    @tool
    def search_code(pattern: str, glob_pattern: str = "**/*") -> str:
        """Search for a text pattern across files in the repository.

        Args:
            pattern: Regular expression or literal string to search for.
            glob_pattern: File glob to filter which files to search
                          (e.g. "**/*.py", "src/**/*.ts"). Default: all files.

        Returns:
            JSON list of matches: [{file, line, text}], max 50 results.
        """
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            # Fall back to literal search
            regex = re.compile(re.escape(pattern), re.IGNORECASE)

        results = []
        try:
            files = list(_root.glob(glob_pattern))
        except Exception:
            files = []

        for fp in files:
            if not fp.is_file():
                continue
            # Skip binary files
            try:
                text = fp.read_text(errors="replace")
            except Exception:
                continue
            rel = str(fp.relative_to(_root))
            for lineno, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    results.append({"file": rel, "line": lineno, "text": line.rstrip()})
                    if len(results) >= 50:
                        break
            if len(results) >= 50:
                break

        return json.dumps(results, indent=2)

    @tool
    def list_directory(path: str = "") -> str:
        """List files and directories inside a repository path.

        Args:
            path: Relative path within the repo. Empty string = repo root.

        Returns:
            Newline-separated list of entries (dirs end with /).
        """
        target = _safe_path(path) if path else _root
        if target is None:
            return f"Error: path {path!r} is outside the repository"
        if not target.exists():
            return f"Directory not found: {path}"
        if not target.is_dir():
            return f"Not a directory: {path}"

        entries = []
        try:
            for child in sorted(target.iterdir()):
                rel = str(child.relative_to(_root))
                if child.is_dir():
                    entries.append(f"{rel}/")
                else:
                    size = child.stat().st_size
                    entries.append(f"{rel}  ({size:,} bytes)")
        except Exception as exc:
            return f"Error listing {path}: {exc}"

        return "\n".join(entries) if entries else "(empty directory)"

    return [read_file, search_code, list_directory]
