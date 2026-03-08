"""TypeScript/JavaScript parser wrapping the TypeScript Compiler API via Node.js subprocess.

The Node.js script `ts_extractor/extractor.js` does the heavy lifting;
this class just calls it and unmarshals the JSON output.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

from src.parsers.base import CallEdge, CodeParser, Dependency, ParsedEntity

logger = logging.getLogger(__name__)

# Path to the Node.js extractor script (sibling directory)
_EXTRACTOR_JS = Path(__file__).parent / "ts_extractor" / "extractor.js"

# Supported extensions
SUPPORTED_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}


def _run_extractor(file_path: str, repo_path: str = "") -> Optional[dict]:
    """Run the Node.js TS extractor and return parsed JSON, or None on failure."""
    if not _EXTRACTOR_JS.exists():
        logger.error("TypeScript extractor not found at %s", _EXTRACTOR_JS)
        return None

    args = ["node", str(_EXTRACTOR_JS), file_path]
    if repo_path:
        args.append(repo_path)

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("TS extractor failed for %s: %s", file_path, result.stderr[:200])
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        logger.warning("TS extractor timed out for %s", file_path)
    except json.JSONDecodeError as exc:
        logger.warning("TS extractor returned invalid JSON for %s: %s", file_path, exc)
    except FileNotFoundError:
        logger.error("'node' not found in PATH — cannot parse TypeScript files")
    except Exception as exc:
        logger.warning("TS extractor unexpected error for %s: %s", file_path, exc)
    return None


class TypeScriptParser(CodeParser):
    """Parser for TypeScript/JavaScript source files using the TS Compiler API."""

    def parse_file(self, file_path: str, repo_path: str = "") -> list[ParsedEntity]:
        """Extract all code entities from a TS/JS file."""
        data = _run_extractor(file_path, repo_path)
        if not data:
            return []

        entities: list[ParsedEntity] = []
        for raw in data.get("entities", []):
            entities.append(
                ParsedEntity(
                    name=raw["name"],
                    qualified_name=raw["qualified_name"],
                    entity_type=raw["entity_type"],
                    file_path=raw["file_path"],
                    line_start=raw.get("line_start", 1),
                    line_end=raw.get("line_end", 1),
                    signature=raw.get("signature"),
                    docstring=raw.get("docstring"),
                    calls=[e["callee"] for e in data.get("call_edges", [])
                           if e.get("caller") == raw["qualified_name"]],
                    imports=[imp["imported_name"] for imp in data.get("imports", [])],
                    entity_metadata=raw.get("entity_metadata", {}),
                )
            )
        return entities

    def resolve_imports(self, file_path: str, repo_path: str = "") -> list[Dependency]:
        """Resolve import statements from a TS/JS file."""
        data = _run_extractor(file_path, repo_path)
        if not data:
            return []

        return [
            Dependency(
                source_file=file_path,
                imported_name=imp["imported_name"],
                resolved_path=imp.get("resolved_path"),
            )
            for imp in data.get("imports", [])
        ]

    def get_call_graph(self, file_path: str, repo_path: str = "") -> list[CallEdge]:
        """Extract call edges from a TS/JS file."""
        data = _run_extractor(file_path, repo_path)
        if not data:
            return []

        return [
            CallEdge(caller=edge["caller"], callee=edge["callee"])
            for edge in data.get("call_edges", [])
            if edge.get("caller") and edge.get("callee")
        ]
