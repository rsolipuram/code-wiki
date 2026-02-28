"""Builders for special wiki pages: getting_started, function_index, glossary, api_reference."""

import json
import logging
import re
from pathlib import Path
from typing import Any

from src.llm.client import chat
from src.parsers.base import ParsedEntity

logger = logging.getLogger(__name__)


def build_getting_started(
    repo_name: str,
    repo_path: str,
    fingerprint_dict: dict,
) -> dict[str, Any]:
    """Extract prerequisites and setup steps from README and config files (FR-007)."""
    # Try reading README first
    readme_content = ""
    for readme in ["README.md", "README.rst", "README.txt", "README"]:
        readme_path = Path(repo_path) / readme
        if readme_path.exists():
            try:
                readme_content = readme_path.read_text(errors="replace")[:4000]
                break
            except OSError:
                pass

    if not readme_content:
        readme_content = f"Repository: {repo_name}\nLanguage: {fingerprint_dict.get('primary_language', 'unknown')}"

    prompt = f"""Extract structured getting-started information from this README.

{readme_content}

Return JSON only:
{{
  "prerequisites": [{{"name": "<tool>", "version": "<version or any>", "description": "<why needed>"}}],
  "setup_steps": [{{"step": <number>, "title": "<title>", "command": "<command or null>", "description": "<desc>"}}],
  "configuration": [{{"key": "<env var>", "description": "<what it does>", "required": <bool>}}],
  "quick_links": [{{"label": "<label>", "url": "<url or path>"}}]
}}"""

    try:
        response = chat(messages=[{"role": "user", "content": prompt}])
        content = json.loads(response)
    except Exception as exc:
        logger.warning("Getting started page build failed: %s", exc)
        content = {
            "prerequisites": [],
            "setup_steps": [{"step": 1, "title": "Clone repository", "command": f"git clone <url>", "description": ""}],
            "configuration": [],
            "quick_links": [],
        }

    content["page_type"] = "getting_started"
    return content


def build_function_index(entities: list[ParsedEntity]) -> dict[str, Any]:
    """Build an alphabetical index of all public code entities (FR-008)."""
    public = [
        e for e in entities
        if not e.name.startswith("_") and e.entity_type in ("function", "class", "method")
    ]
    public.sort(key=lambda e: e.name.lower())

    # Group by first letter
    index: dict[str, list[dict]] = {}
    for entity in public:
        letter = entity.name[0].upper() if entity.name else "#"
        index.setdefault(letter, []).append({
            "name": entity.name,
            "qualified_name": entity.qualified_name,
            "type": entity.entity_type,
            "file": entity.file_path,
            "line": entity.line_start,
            "signature": entity.signature,
            "summary": (entity.docstring or "").split("\n")[0][:100] if entity.docstring else "",
        })

    return {
        "page_type": "function_index",
        "total_count": len(public),
        "index": index,
    }


def build_glossary(entities: list[ParsedEntity], repo_path: str) -> dict[str, Any]:
    """Extract domain terms from docstrings and comments (FR-009)."""
    # Collect all docstrings
    all_docs = " ".join(
        e.docstring for e in entities if e.docstring
    )[:6000]

    if not all_docs.strip():
        return {"page_type": "glossary", "terms": [], "total_count": 0}

    prompt = f"""Extract a glossary of domain-specific terms from these code docstrings.

{all_docs}

Return JSON only:
{{
  "terms": [
    {{
      "term": "<term>",
      "type": "concept|pattern|acronym|entity",
      "definition": "<1-2 sentence definition>",
      "related_terms": ["<term>", ...]
    }},
    ...
  ]
}}

Include: domain concepts, business terms, technical patterns, acronyms.
Exclude: generic programming terms (function, class, method, etc.)."""

    try:
        response = chat(messages=[{"role": "user", "content": prompt}])
        data = json.loads(response)
        terms = data.get("terms", [])
    except Exception as exc:
        logger.warning("Glossary build failed: %s", exc)
        terms = []

    # Sort alphabetically
    terms.sort(key=lambda t: t.get("term", "").lower())

    return {
        "page_type": "glossary",
        "terms": terms,
        "total_count": len(terms),
    }


def build_api_reference(entities: list[ParsedEntity]) -> dict[str, Any]:
    """Build alphabetical API reference index (FR-008)."""
    api_entities = [
        e for e in entities
        if not e.name.startswith("_") and e.entity_type in ("function", "class")
    ]
    api_entities.sort(key=lambda e: e.name.lower())

    # Group by first letter
    index: dict[str, list[dict]] = {}
    for entity in api_entities:
        letter = entity.name[0].upper() if entity.name else "#"
        index.setdefault(letter, []).append({
            "name": entity.name,
            "qualified_name": entity.qualified_name,
            "type": entity.entity_type,
            "file": entity.file_path,
            "line": entity.line_start,
            "signature": entity.signature,
            "description": (entity.docstring or "").split("\n")[0][:200] if entity.docstring else "",
            "visibility": "public",
        })

    return {
        "page_type": "api_reference",
        "total_count": len(api_entities),
        "index": index,
    }
