"""Builders for special wiki pages: getting_started, function_index, glossary, api_reference."""

import json
import logging
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.llm.client import chat
from src.parsers.base import ParsedEntity

logger = logging.getLogger(__name__)


def _extract_json_payload(text: str) -> dict[str, Any]:
    """Parse JSON object from model output, tolerating wrapped content."""
    stripped = (text or "").strip()
    if not stripped:
        raise ValueError("empty_response")
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if not match:
        raise ValueError("non_json_response")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("json_not_object")
    return data


def _chat_json_with_retries(
    prompt: str,
    page_kind: str,
    max_attempts: int = 3,
    analysis_id: str | None = None,
) -> tuple[dict[str, Any], int]:
    """Call LLM and parse JSON with bounded retries and telemetry logs."""
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        call_id = uuid4().hex[:12]
        try:
            response = chat(
                messages=[{"role": "user", "content": prompt}],
                cache_ttl=None,  # avoid caching malformed/empty transient responses
                trace_context={
                    "stage": "special_page",
                    "component": page_kind,
                    "call_id": call_id,
                    "analysis_id": analysis_id,
                },
            )
            parsed = _extract_json_payload(response)
            logger.info(
                "LLM_TELEMETRY %s",
                json.dumps(
                    {
                        "event": "special_page_parse",
                        "status": "success",
                        "page_kind": page_kind,
                        "attempt": attempt,
                        "call_id": call_id,
                        "response_chars": len(response or ""),
                        "parse_outcome": "json_object",
                    },
                    sort_keys=True,
                ),
            )
            return parsed, attempt
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning(
                "Special page JSON parse failed (%s attempt %d/%d): %s",
                page_kind,
                attempt,
                max_attempts,
                exc,
            )
            logger.warning(
                "LLM_TELEMETRY %s",
                json.dumps(
                    {
                        "event": "special_page_parse",
                        "status": "failure",
                        "page_kind": page_kind,
                        "attempt": attempt,
                        "call_id": call_id,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:300],
                        "parse_outcome": "invalid_json",
                    },
                    sort_keys=True,
                ),
            )

    raise RuntimeError(f"{page_kind} generation failed after {max_attempts} attempts") from last_exc


def build_getting_started(
    repo_name: str,
    repo_path: str,
    fingerprint_dict: dict,
    repo_url: str | None = None,
    analysis_id: str | None = None,
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
        content, attempts_used = _chat_json_with_retries(
            prompt,
            "getting_started",
            max_attempts=3,
            analysis_id=analysis_id,
        )
        content = _sanitize_getting_started_content(
            content,
            repo_name=repo_name,
            repo_url=repo_url,
            repo_dir=repo_dir,
            fingerprint_dict=fingerprint_dict,
        )
        content["_meta"] = {"fallback_used": False, "attempts": attempts_used}
    except Exception as exc:
        logger.warning("Getting started page build failed: %s", exc)
        content = _fallback_getting_started(
            repo_name=repo_name,
            repo_url=repo_url,
            repo_dir=repo_dir,
            fingerprint_dict=fingerprint_dict,
        )
        content["_meta"] = {
            "fallback_used": True,
            "error_type": type(exc).__name__,
            "error": str(exc)[:300],
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

    # Deduplicate by source location to collapse duplicate method/function entries
    # that point at the same symbol on the same line.
    public = _dedupe_entities_by_location(
        public,
        repo_path=repo_path,
        type_preference={"method": 0, "function": 1, "class": 2},
    )

    total_count = len(public)
    if len(public) > max_entities:
        logger.info("Function index: capping from %d to %d entities", len(public), max_entities)
        public = public[:max_entities]

    # Group by first letter
    index: dict[str, list[dict]] = {}
    for entity in public:
        letter = entity.name[0].upper() if entity.name else "#"
        summary = (entity.docstring or "").split("\n")[0][:100] if entity.docstring else ""
        if not summary:
            summary = f"{entity.entity_type.title()} `{entity.name}` in `{_rel_path(entity.file_path, repo_path)}`."
        index.setdefault(letter, []).append({
            "name": entity.name,
            "qualified_name": entity.qualified_name,
            "type": entity.entity_type,
            "file": _rel_path(entity.file_path, repo_path),
            "line": entity.line_start,
            "signature": entity.signature,
            "summary": summary,
        })

    return {
        "page_type": "function_index",
        "version": 2,
        "total_count": total_count,
        "shown_count": len(public),
        "index": index,
    }


def build_glossary(
    entities: list[ParsedEntity],
    repo_path: str,
    system_narrative: str = "",
    module_prose: list[str] | None = None,
    analysis_id: str | None = None,
) -> dict[str, Any]:
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
        data, attempts_used = _chat_json_with_retries(
            prompt,
            "glossary",
            max_attempts=3,
            analysis_id=analysis_id,
        )
        terms = data.get("terms", [])
        meta = {"fallback_used": False, "attempts": attempts_used}
    except Exception as exc:
        logger.warning("Glossary build failed: %s", exc)
        terms = []
        meta = {
            "fallback_used": True,
            "error_type": type(exc).__name__,
            "error": str(exc)[:300],
        }

    # Sort alphabetically
    terms.sort(key=lambda t: t.get("term", "").lower())

    return {
        "page_type": "glossary",
        "version": 2,
        "terms": terms,
        "total_count": len(terms),
        "_meta": meta,
    }


def build_api_reference(entities: list[ParsedEntity], repo_path: str = "") -> dict[str, Any]:
    """Build endpoint/API-oriented reference index (FR-008)."""
    api_entities = [
        e for e in entities
        if not e.name.startswith("_") and e.entity_type in ("function", "class", "method")
    ]

    def _is_api_like(entity: ParsedEntity) -> bool:
        rel_path = _rel_path(entity.file_path, repo_path).lower()
        metadata = getattr(entity, "entity_metadata", {}) or {}
        decorators = metadata.get("decorators", [])
        route_decorator_re = re.compile(r"\b(?:router|app)\.(?:get|post|put|delete|patch|options|head)\s*\(")
        if isinstance(decorators, list):
            for dec in decorators:
                dec_str = str(dec).lower()
                if route_decorator_re.search(dec_str):
                    return True

        # Prefer strong path-based API heuristics over broad keyword fallback.
        api_path_hint = bool(
            re.search(r"(?:^|/)(api|routes?|controllers?|handlers?|endpoints?)(?:/|$)", rel_path)
            or rel_path.endswith(("/server.py", "/server.ts", "/server.js"))
        )
        if not api_path_hint:
            return False

        name = (entity.name or "").lower()
        qname = (entity.qualified_name or "").lower()
        signature = (entity.signature or "").lower()
        api_keywords = ("route", "endpoint", "request", "response", "handler", "api", "http")
        http_verbs = ("get", "post", "put", "delete", "patch", "options", "head")
        if any(v in name or v in signature for v in http_verbs):
            return True
        return any(k in name or k in qname or k in signature for k in api_keywords)

    api_entities = [e for e in api_entities if _is_api_like(e)]
    api_entities.sort(key=lambda e: e.name.lower())

    api_entities = _dedupe_entities_by_location(
        api_entities,
        repo_path=repo_path,
        type_preference={"class": 0, "function": 1},
    )

    # Group by first letter
    index: dict[str, list[dict]] = {}
    for entity in api_entities:
        letter = entity.name[0].upper() if entity.name else "#"
        description = (entity.docstring or "").split("\n")[0][:200] if entity.docstring else ""
        if not description:
            description = f"{entity.entity_type.title()} `{entity.name}` declared in `{_rel_path(entity.file_path, repo_path)}`."
        index.setdefault(letter, []).append({
            "name": entity.name,
            "qualified_name": entity.qualified_name,
            "type": entity.entity_type,
            "file": _rel_path(entity.file_path, repo_path),
            "line": entity.line_start,
            "signature": entity.signature,
            "description": description,
            "visibility": "public",
        })

    return {
        "page_type": "api_reference",
        "version": 2,
        "total_count": len(api_entities),
        "index": index,
    }


def _is_placeholder(value: str | None) -> bool:
    if not value:
        return True
    normalized = value.strip().lower()
    if not normalized:
        return True
    return bool(
        re.search(r"<[^>]+>", normalized)
        or "repo-url" in normalized
        or normalized in {"tbd", "todo", "placeholder"}
    )


def _default_clone_url(repo_name: str, repo_url: str | None) -> str:
    if repo_url and repo_url.strip():
        return repo_url.strip()
    guessed = repo_name.strip().replace(" ", "-")
    return f"https://github.com/{guessed}/{guessed}.git"


def _infer_default_setup_steps(
    repo_name: str,
    repo_url: str | None,
    repo_dir: Path,
) -> list[dict[str, Any]]:
    clone_url = _default_clone_url(repo_name, repo_url)
    steps: list[dict[str, Any]] = [
        {
            "step": 1,
            "title": "Clone repository",
            "command": f"git clone {clone_url}",
            "description": f"Clone the {repo_name} repository locally.",
        },
        {
            "step": 2,
            "title": "Enter project directory",
            "command": f"cd {repo_name}",
            "description": "Switch into the repository root directory.",
        },
    ]

    has_docker = (repo_dir / "docker-compose.yml").exists() or (repo_dir / "docker-compose.yaml").exists()
    has_frontend = (repo_dir / "frontend" / "package.json").exists()
    has_backend_reqs = (repo_dir / "backend" / "requirements.txt").exists()
    has_backend_pyproject = (repo_dir / "backend" / "pyproject.toml").exists()
    has_root_package = (repo_dir / "package.json").exists()

    if has_docker:
        steps.append(
            {
                "step": len(steps) + 1,
                "title": "Start services",
                "command": "docker-compose up -d",
                "description": "Start required local services in detached mode.",
            }
        )

    if has_backend_reqs or has_backend_pyproject:
        install_cmd = "pip install -r requirements.txt" if has_backend_reqs else "pip install -e ."
        steps.append(
            {
                "step": len(steps) + 1,
                "title": "Install backend dependencies",
                "command": f"cd backend && {install_cmd}",
                "description": "Install Python dependencies for the backend service.",
            }
        )
        steps.append(
            {
                "step": len(steps) + 1,
                "title": "Run backend",
                "command": "cd backend && uvicorn src.api.main:app --reload --port 8000",
                "description": "Start the backend API server.",
            }
        )

    if has_frontend:
        steps.append(
            {
                "step": len(steps) + 1,
                "title": "Run frontend",
                "command": "cd frontend && npm install && npm run dev",
                "description": "Install frontend dependencies and start the web UI.",
            }
        )
    elif has_root_package:
        steps.append(
            {
                "step": len(steps) + 1,
                "title": "Run application",
                "command": "npm install && npm run dev",
                "description": "Install dependencies and start the application.",
            }
        )

    return steps


def _infer_quick_links(repo_url: str | None, repo_dir: Path) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    if repo_url and repo_url.strip():
        links.append({"label": "Repository", "url": repo_url.strip()})
    if (repo_dir / "README.md").exists():
        links.append({"label": "README", "url": "README.md"})
    if (repo_dir / "docker-compose.yml").exists():
        links.append({"label": "Docker Compose", "url": "docker-compose.yml"})
    elif (repo_dir / "docker-compose.yaml").exists():
        links.append({"label": "Docker Compose", "url": "docker-compose.yaml"})
    if (repo_dir / ".env.example").exists():
        links.append({"label": "Environment Example", "url": ".env.example"})
    elif (repo_dir / ".env.sample").exists():
        links.append({"label": "Environment Example", "url": ".env.sample"})
    return links


def _sanitize_getting_started_content(
    content: dict[str, Any],
    repo_name: str,
    repo_url: str | None,
    repo_dir: Path,
    fingerprint_dict: dict[str, Any],
) -> dict[str, Any]:
    sanitized = dict(content)
    defaults = _infer_default_setup_steps(repo_name, repo_url, repo_dir)

    setup_steps = sanitized.get("setup_steps", [])
    if not isinstance(setup_steps, list):
        setup_steps = []

    clean_steps: list[dict[str, Any]] = []
    for i, raw in enumerate(setup_steps):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title", "")).strip() or f"Step {i + 1}"
        command = raw.get("command")
        description = str(raw.get("description", "")).strip()
        if command is not None:
            command = str(command).strip()
        if _is_placeholder(command):
            command = defaults[i]["command"] if i < len(defaults) else None
        clean_steps.append(
            {
                "step": i + 1,
                "title": title,
                "command": command,
                "description": description,
            }
        )

    if not clean_steps:
        clean_steps = defaults

    prerequisites = sanitized.get("prerequisites", [])
    if not isinstance(prerequisites, list):
        prerequisites = []
    if not prerequisites:
        lang = str(fingerprint_dict.get("primary_language", "")).lower()
        inferred = []
        if lang in {"python"} or (repo_dir / "backend" / "requirements.txt").exists():
            inferred.append({"name": "Python", "version": "3.11+", "description": "Required for backend services."})
        if (repo_dir / "frontend" / "package.json").exists() or (repo_dir / "package.json").exists():
            inferred.append({"name": "Node.js", "version": "18+", "description": "Required for frontend tooling and runtime."})
        if (repo_dir / "docker-compose.yml").exists() or (repo_dir / "docker-compose.yaml").exists():
            inferred.append({"name": "Docker", "version": "latest", "description": "Required to run local dependencies."})
        prerequisites = inferred

    quick_links = sanitized.get("quick_links", [])
    if not isinstance(quick_links, list):
        quick_links = []
    quick_links = [q for q in quick_links if isinstance(q, dict) and not _is_placeholder(str(q.get("url", "")))]
    if not quick_links:
        quick_links = _infer_quick_links(repo_url, repo_dir)

    config = sanitized.get("configuration", [])
    if not isinstance(config, list):
        config = []

    sanitized["prerequisites"] = prerequisites
    sanitized["setup_steps"] = clean_steps
    sanitized["configuration"] = config
    sanitized["quick_links"] = quick_links
    return sanitized


def _fallback_getting_started(
    repo_name: str,
    repo_url: str | None,
    repo_dir: Path,
    fingerprint_dict: dict[str, Any],
) -> dict[str, Any]:
    return {
        "prerequisites": _sanitize_getting_started_content(
            {"prerequisites": [], "setup_steps": [], "configuration": [], "quick_links": []},
            repo_name=repo_name,
            repo_url=repo_url,
            repo_dir=repo_dir,
            fingerprint_dict=fingerprint_dict,
        )["prerequisites"],
        "setup_steps": _infer_default_setup_steps(repo_name, repo_url, repo_dir),
        "configuration": [],
        "quick_links": _infer_quick_links(repo_url, repo_dir),
    }


def _dedupe_entities_by_location(
    entities: list[ParsedEntity],
    repo_path: str,
    type_preference: dict[str, int],
) -> list[ParsedEntity]:
    best_by_location: dict[tuple[str, str, int], ParsedEntity] = {}
    for entity in entities:
        rel_file = _rel_path(entity.file_path, repo_path)
        key = (entity.name.lower(), rel_file, entity.line_start)
        current = best_by_location.get(key)
        if current is None:
            best_by_location[key] = entity
            continue
        current_rank = type_preference.get(current.entity_type, 99)
        incoming_rank = type_preference.get(entity.entity_type, 99)
        if incoming_rank < current_rank:
            best_by_location[key] = entity

    deduped = list(best_by_location.values())
    deduped.sort(
        key=lambda e: (
            e.name.lower(),
            _rel_path(e.file_path, repo_path),
            e.line_start,
            type_preference.get(e.entity_type, 99),
        )
    )
    return deduped
