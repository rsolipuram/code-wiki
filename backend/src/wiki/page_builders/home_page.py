"""Home page builder — creates the repository wiki home page (page_type=home)."""

from typing import Any

from src.parsers.base import ParsedEntity
from src.recon.fingerprint import RepoFingerprint


def build_home_page(
    repo_name: str,
    repo_url: str,
    fingerprint: RepoFingerprint,
    modules: list[dict],  # [{name, slug, description, file_count}]
    entities: list[ParsedEntity],
    commit_hash: str | None = None,
) -> dict[str, Any]:
    """Build structured home page content (matches WikiPage JSONB schema).

    Sections: overview, stats, quick_links, module_list, recent_activity
    """
    function_count = sum(1 for e in entities if e.entity_type == "function")
    class_count = sum(1 for e in entities if e.entity_type == "class")
    method_count = sum(1 for e in entities if e.entity_type == "method")

    return {
        "page_type": "home",
        "overview": {
            "name": repo_name,
            "url": repo_url,
            "project_description": getattr(fingerprint, "project_description", ""),
            "primary_language": fingerprint.primary_language,
            "languages": fingerprint.languages[:6],
            "system_type": fingerprint.system_type,
            "tools": fingerprint.tools_present[:8],
        },
        "stats": {
            "modules": len(modules),
            "files": fingerprint.file_count,
            "loc": fingerprint.loc,
            "functions": function_count,
            "classes": class_count,
            "methods": method_count,
        },
        "quick_links": [
            {"label": "Getting Started", "slug": "getting-started", "icon": "rocket"},
            {"label": "API Reference", "slug": "api-reference", "icon": "code"},
            {"label": "Architecture", "slug": "architecture", "icon": "diagram"},
            {"label": "Glossary", "slug": "glossary", "icon": "book"},
        ],
        "module_list": modules,
        "commit_hash": commit_hash,
    }
