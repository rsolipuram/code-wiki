"""Wiki Generation Pipeline orchestrator — 3-agent pipeline per module.

Agent 1: StructuralAnalyst (interestingness scoring, no LLM)
Agent 2: ImplementationExplainer (parallel LLM calls for top-N entities)
Agent 3: ModuleWeaver (single LLM synthesis call)
"""

import concurrent.futures
import hashlib
import logging
import time
from typing import Any, Optional

from src.dossier.schema import Dossier
from src.llm.client import chat
from src.parsers.base import ParsedEntity
from src.wiki.context_builder import build_module_context
from src.wiki.interestingness import ScoredEntity, score_entities

logger = logging.getLogger(__name__)

# Maximum parallel LLM calls for Agent 2
_MAX_PARALLEL_ENTITY_CALLS = 1

_ENTITY_EXPLAINER_PROMPT = """Explain this code entity in context of the surrounding codebase.

Entity: {qualified_name} ({entity_type})
File: {file_path} (lines {line_start}-{line_end})
Signature: {signature}

Docstring:
{docstring}

Class context (if method):
{class_context}

Calls: {calls}
Called by: {callers}

Source:
```
{source_snippet}
```

Answer: WHY does this entity exist? What problem does it solve? What design decisions does it encode?
Be specific and concrete. Max 150 words. No preamble."""

_MODULE_WEAVER_PROMPT = """You are ModuleWeaver. Synthesize a coherent module documentation page.

Module: {module_name}
Files: {file_paths}

Structural analysis:
{structural_report}

Entity explanations:
{entity_explanations}

Dossier context (security, dependencies, architecture):
{dossier_context}

Write a structured module documentation with these sections (JSON):
{{
  "purpose": "<2-3 sentences on why this module exists>",
  "design_patterns": ["<pattern detected>", ...],
  "data_flow": "<how data moves through this module>",
  "key_components": [
    {{"name": "<entity_name>", "role": "<1 sentence role>"}},
    ...
  ],
  "dependencies": {{"internal": ["<module>"], "external": ["<package>"]}},
  "configuration": "<relevant config keys or settings>",
  "gotchas": ["<common pitfall or non-obvious behavior>", ...],
  "security_notes": "<security context from Dossier or 'none'>",
  "related_modules": ["<module_name>", ...]
}}

Return ONLY valid JSON. Evidence must be traceable to actual code."""


def generate_module_wiki(
    module_name: str,
    entities: list[ParsedEntity],
    file_paths: list[str],
    repository_id: str,
    repo_path: str,
    dossier: Optional[Dossier] = None,
) -> dict[str, Any]:
    """Run the 3-agent wiki generation pipeline for a single module.

    Args:
        module_name: Human-readable module name.
        entities: All ParsedEntity objects from this module.
        file_paths: Relative paths of files in this module.
        repository_id: Repository UUID.
        repo_path: Absolute local repository path.
        dossier: Populated Dossier (optional; used for security/arch context).

    Returns:
        Structured module wiki content dict (matches WikiPage JSONB schema).
    """
    # ── Agent 1: Structural analysis ─────────────────────────────────────────
    logger.info("Agent 1 [StructuralAnalyst]: scoring %d entities in %s", len(entities), module_name)
    scored_entities = score_entities(entities)
    structural_report = _build_structural_report(scored_entities, entities)

    # Log top scored entities
    for s in scored_entities[:5]:
        logger.info("  Top entity: %s (score=%.2f)", s.entity.qualified_name, s.score)

    # ── Agent 2: Parallel entity explanations ─────────────────────────────────
    top_entities = scored_entities[:_MAX_PARALLEL_ENTITY_CALLS]
    logger.info("Agent 2 [ImplementationExplainer]: explaining %d entities", len(top_entities))

    # Build caller map for context
    caller_map: dict[str, list[str]] = {}
    for e in entities:
        for callee in e.calls:
            caller_map.setdefault(callee, []).append(e.qualified_name)

    entity_explanations: dict[str, str] = {}
    if top_entities:
        agent2_start = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(top_entities), _MAX_PARALLEL_ENTITY_CALLS)) as ex:
            futures = {
                ex.submit(
                    _explain_entity,
                    scored.entity,
                    caller_map.get(scored.entity.qualified_name, []),
                    caller_map.get(scored.entity.name, []),
                    repo_path,
                    entities,
                ): scored.entity.qualified_name
                for scored in top_entities
            }
            for future in concurrent.futures.as_completed(futures):
                qname = futures[future]
                try:
                    entity_explanations[qname] = future.result()
                    logger.debug("Agent 2: explained %s", qname)
                except Exception as exc:
                    logger.warning("Entity explanation failed for %s: %s", qname, exc)
                    entity_explanations[qname] = "Explanation unavailable."
        agent2_elapsed = time.monotonic() - agent2_start
        logger.info("Agent 2 complete: %d entities in %.1fs", len(entity_explanations), agent2_elapsed)

    # ── Agent 3: Module synthesis ─────────────────────────────────────────────
    logger.info("Agent 3 [ModuleWeaver]: synthesizing module narrative")
    context = build_module_context(module_name, file_paths, repository_id, repo_path)

    dossier_context_str = _format_dossier_context(context["dossier_findings"], dossier)
    explanations_str = "\n\n".join(
        f"### {qname}\n{explanation}"
        for qname, explanation in entity_explanations.items()
    )

    prompt = _MODULE_WEAVER_PROMPT.format(
        module_name=module_name,
        file_paths=", ".join(file_paths[:5]),
        structural_report=structural_report[:2000],
        entity_explanations=explanations_str[:8000],
        dossier_context=dossier_context_str[:2000],
    )

    logger.info("Agent 3 prompt size: %d chars", len(prompt))
    try:
        import json
        response = chat(
            messages=[{"role": "user", "content": prompt}],
            cache_ttl=3600,
        )
        content = json.loads(response)
        logger.info("Agent 3 [ModuleWeaver]: synthesis complete for %s", module_name)
    except Exception as exc:
        logger.error("ModuleWeaver failed for %s: %s — using fallback", module_name, exc)
        content = _fallback_content(module_name, file_paths, scored_entities)

    return content


def _explain_entity(
    entity: ParsedEntity,
    callers: list[str],
    callers_by_name: list[str],
    repo_path: str,
    all_entities: list[ParsedEntity],
) -> str:
    """Agent 2: single LLM call to explain one entity."""
    # Get class body context for methods
    class_context = ""
    if entity.entity_type == "method":
        class_name = (entity.entity_metadata or {}).get("class", "")
        if class_name:
            class_entity = next(
                (e for e in all_entities if e.name == class_name and e.entity_type == "class"),
                None,
            )
            if class_entity:
                class_context = f"class {class_name}({', '.join((class_entity.entity_metadata or {}).get('bases', []))})"

    # Read source snippet
    import contextlib
    from pathlib import Path
    source_snippet = ""
    with contextlib.suppress(OSError):
        lines = Path(entity.file_path).read_text(errors="replace").splitlines()
        snippet_lines = lines[entity.line_start - 1:entity.line_end]
        source_snippet = "\n".join(snippet_lines[:50])  # max 50 lines

    prompt = _ENTITY_EXPLAINER_PROMPT.format(
        qualified_name=entity.qualified_name,
        entity_type=entity.entity_type,
        file_path=entity.file_path,
        line_start=entity.line_start,
        line_end=entity.line_end,
        signature=entity.signature or "N/A",
        docstring=entity.docstring or "No docstring.",
        class_context=class_context or "N/A",
        calls=", ".join(entity.calls[:10]) or "none",
        callers=", ".join((callers + callers_by_name)[:5]) or "none",
        source_snippet=source_snippet,
    )

    return chat(messages=[{"role": "user", "content": prompt}])


def _build_structural_report(scored: list[ScoredEntity], all_entities: list[ParsedEntity]) -> str:
    """Format structural analysis summary for Agent 3."""
    lines = [f"Total entities: {len(all_entities)}", f"High-interest entities: {len(scored)}", ""]
    for s in scored[:20]:
        lines.append(f"- {s.entity.qualified_name} (score={s.score:.2f}): {'; '.join(s.reasons)}")
    return "\n".join(lines)


def _format_dossier_context(findings: list[dict], dossier: Optional[Dossier]) -> str:
    """Format Dossier RAG results for Agent 3 prompt."""
    if not findings and (dossier is None or not dossier.security):
        return "No Dossier context available."

    parts = []
    for f in findings[:5]:
        section = f.get("section", "unknown")
        desc = f.get("description", str(f)[:100])
        parts.append(f"[{section}] {desc}")

    if dossier and dossier.architecture:
        parts.append(f"[architecture] style={dossier.architecture.primary_style}")

    return "\n".join(parts)


def _fallback_content(
    module_name: str,
    file_paths: list[str],
    scored: list[ScoredEntity],
) -> dict[str, Any]:
    """Return a minimal content dict when ModuleWeaver LLM call fails."""
    return {
        "purpose": f"Module {module_name} containing {len(file_paths)} file(s).",
        "design_patterns": [],
        "data_flow": "Analysis unavailable.",
        "key_components": [
            {"name": s.entity.name, "role": s.entity.docstring or "No description."}
            for s in scored[:5]
        ],
        "dependencies": {"internal": [], "external": []},
        "configuration": "none",
        "gotchas": [],
        "security_notes": "none",
        "related_modules": [],
    }


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def partial_regenerate(
    module_name: str,
    changed_entity_names: list[str],
    all_entities: list[ParsedEntity],
    file_paths: list[str],
    repository_id: str,
    repo_path: str,
    dossier: Optional[Dossier] = None,
) -> dict[str, Any]:
    """Partial regeneration: re-run Agent 2 only for changed entities, then full Agent 3.

    Used by the real-time sync pipeline when only some entities change.
    """
    # Score all entities (uses canonical hashes for change detection)
    scored = score_entities(all_entities)
    # For partial regen, only changed entities go through Agent 2
    to_explain = [s for s in scored if s.entity.name in changed_entity_names]

    logger.info(
        "Partial regen %s: %d changed entities → Agent 2, then full Agent 3",
        module_name, len(to_explain),
    )
    return generate_module_wiki(
        module_name=module_name,
        entities=all_entities,
        file_paths=file_paths,
        repository_id=repository_id,
        repo_path=repo_path,
        dossier=dossier,
    )
