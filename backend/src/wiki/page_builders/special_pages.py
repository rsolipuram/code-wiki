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
    repo_dir = Path(repo_path)

    # Read README
    readme_content = ""
    for readme in ["README.md", "README.rst", "README.txt", "README"]:
        readme_path = repo_dir / readme
        if readme_path.exists():
            try:
                readme_content = readme_path.read_text(errors="replace")[:3000]
                break
            except OSError:
                pass

    # Read additional config files that reveal setup requirements
    extra_files: list[str] = []
    for candidate in [
        "docker-compose.yml", "docker-compose.yaml",
        "Makefile", "makefile",
        "package.json", "pyproject.toml", "requirements.txt",
        ".env.example", ".env.sample", ".env.template",
    ]:
        p = repo_dir / candidate
        if p.exists():
            try:
                snippet = p.read_text(errors="replace")[:800]
                extra_files.append(f"--- {candidate} ---\n{snippet}")
            except OSError:
                pass

    context_parts = []
    if readme_content:
        context_parts.append(f"## README\n{readme_content}")
    if extra_files:
        context_parts.append("## Config files\n" + "\n\n".join(extra_files[:4]))
    if not context_parts:
        context_parts.append(f"Repository: {repo_name}\nLanguage: {fingerprint_dict.get('primary_language', 'unknown')}")

    full_context = "\n\n".join(context_parts)

    prompt = f"""Extract structured getting-started information from this repository.

{full_context}

Return JSON only:
{{
  "prerequisites": [{{"name": "<tool>", "version": "<version or any>", "description": "<why needed>"}}],
  "setup_steps": [{{"step": <number>, "title": "<title>", "command": "<command or null>", "description": "<desc>"}}],
  "configuration": [{{"key": "<env var or config key>", "description": "<what it does>", "required": <bool>}}],
  "quick_links": [{{"label": "<label>", "url": "<url or path>"}}]
}}

Use docker-compose.yml for service setup steps, Makefile for build/run commands, .env.example for configuration keys."""

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
    content["version"] = 2
    return content


def _rel_path(file_path: str, repo_path: str) -> str:
    """Convert absolute cache path to repo-relative path."""
    if not repo_path:
        return file_path
    try:
        return str(Path(file_path).resolve().relative_to(Path(repo_path).resolve()))
    except ValueError:
        return file_path


def build_function_index(entities: list[ParsedEntity], repo_path: str = "", max_entities: int = 500) -> dict[str, Any]:
    """Build an alphabetical index of all public code entities (FR-008).

    Caps at max_entities to prevent oversized pages on large repos.
    """
    public = [
        e for e in entities
        if not e.name.startswith("_") and e.entity_type in ("function", "class", "method")
    ]
    public.sort(key=lambda e: e.name.lower())

    # Deduplicate by qualified_name (a method may appear as both method and function)
    seen: set[str] = set()
    deduped = []
    for entity in public:
        if entity.qualified_name not in seen:
            seen.add(entity.qualified_name)
            deduped.append(entity)
    public = deduped

    total_count = len(public)
    if len(public) > max_entities:
        logger.info("Function index: capping from %d to %d entities", len(public), max_entities)
        public = public[:max_entities]

    # Group by first letter
    index: dict[str, list[dict]] = {}
    for entity in public:
        letter = entity.name[0].upper() if entity.name else "#"
        index.setdefault(letter, []).append({
            "name": entity.name,
            "qualified_name": entity.qualified_name,
            "type": entity.entity_type,
            "file": _rel_path(entity.file_path, repo_path),
            "line": entity.line_start,
            "signature": entity.signature,
            "summary": (entity.docstring or "").split("\n")[0][:100] if entity.docstring else "",
        })

    return {
        "page_type": "function_index",
        "version": 2,
        "total_count": total_count,
        "shown_count": len(public),
        "index": index,
    }


def build_glossary(entities: list[ParsedEntity], repo_path: str, system_narrative: str = "", module_prose: list[str] | None = None) -> dict[str, Any]:
    """Extract domain terms from docstrings, narrative prose, and wiki content (FR-009)."""
    # Collect all docstrings
    docstring_text = " ".join(
        e.docstring for e in entities if e.docstring
    )[:3000]

    # Use module prose segments if provided (much richer than docstrings alone)
    prose_text = ""
    if module_prose:
        prose_text = " ".join(module_prose)[:3000]

    narrative_snippet = system_narrative[:2000] if system_narrative else ""

    all_docs = "\n\n".join(filter(None, [narrative_snippet, prose_text, docstring_text]))[:6000]

    if not all_docs.strip():
        return {"page_type": "glossary", "version": 2, "terms": [], "total_count": 0}

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
        "version": 2,
        "terms": terms,
        "total_count": len(terms),
    }


def build_api_reference(entities: list[ParsedEntity], repo_path: str = "") -> dict[str, Any]:
    """Build alphabetical API reference index (FR-008)."""
    api_entities = [
        e for e in entities
        if not e.name.startswith("_") and e.entity_type in ("function", "class")
    ]
    api_entities.sort(key=lambda e: e.name.lower())

    # Deduplicate by qualified_name
    seen_api: set[str] = set()
    deduped_api = []
    for entity in api_entities:
        if entity.qualified_name not in seen_api:
            seen_api.add(entity.qualified_name)
            deduped_api.append(entity)
    api_entities = deduped_api

    # Group by first letter
    index: dict[str, list[dict]] = {}
    for entity in api_entities:
        letter = entity.name[0].upper() if entity.name else "#"
        index.setdefault(letter, []).append({
            "name": entity.name,
            "qualified_name": entity.qualified_name,
            "type": entity.entity_type,
            "file": _rel_path(entity.file_path, repo_path),
            "line": entity.line_start,
            "signature": entity.signature,
            "description": (entity.docstring or "").split("\n")[0][:200] if entity.docstring else "",
            "visibility": "public",
        })

    return {
        "page_type": "api_reference",
        "version": 2,
        "total_count": len(api_entities),
        "index": index,
    }
