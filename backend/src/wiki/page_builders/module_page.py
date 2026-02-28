"""Module page builder — creates module documentation pages (page_type=module)."""

import re
from typing import Any

from src.parsers.base import ParsedEntity


def slugify(name: str) -> str:
    """Convert module name to URL-safe slug."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def build_module_page(
    module_name: str,
    wiki_content: dict[str, Any],  # output from wiki orchestrator
    entities: list[ParsedEntity],
    file_paths: list[str],
    dependencies_modules: list[str] = None,
    commit_hash: str | None = None,
) -> dict[str, Any]:
    """Build structured module page content (8 sections per spec FR-010).

    Sections: overview, location, how_it_works, key_components, dependencies,
              configuration, related_pages, known_issues
    """
    # Extract public entities for key components section
    public_entities = [
        e for e in entities
        if not e.name.startswith("_") and e.entity_type in ("function", "class", "method")
    ][:20]

    return {
        "page_type": "module",
        "overview": {
            "purpose": wiki_content.get("purpose", ""),
            "design_patterns": wiki_content.get("design_patterns", []),
            "data_flow": wiki_content.get("data_flow", ""),
        },
        "location": {
            "files": file_paths,
            "file_count": len(file_paths),
            "primary_file": file_paths[0] if file_paths else None,
        },
        "how_it_works": wiki_content.get("data_flow", ""),
        "key_components": wiki_content.get("key_components", [
            {"name": e.name, "role": e.docstring or e.signature or ""}
            for e in public_entities[:8]
        ]),
        "dependencies": wiki_content.get("dependencies", {"internal": [], "external": []}),
        "configuration": wiki_content.get("configuration", ""),
        "related_pages": [
            {"name": m, "slug": slugify(m)}
            for m in wiki_content.get("related_modules", [])
        ],
        "known_issues": wiki_content.get("gotchas", []),
        "security_notes": wiki_content.get("security_notes", ""),
        "commit_hash": commit_hash,
    }


def build_dashboard_page(
    repo_name: str,
    modules: list[dict],
) -> dict[str, Any]:
    """Build a high-level dashboard/index page for module navigation."""
    return {
        "page_type": "home",
        "title": f"{repo_name} — Module Overview",
        "modules": modules,
        "module_count": len(modules),
    }
