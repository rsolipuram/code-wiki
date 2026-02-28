"""StructuralAnalyst (Agent 1) — rule-based interestingness scoring.

Scores code entities 0.0–1.0 based on:
- Call-in-degree (many callers)
- Cyclomatic complexity (many branches)
- Cross-module dependencies
- Public API surface
- Unusual patterns (decorators, generators, context managers)

Zero LLM calls. Produces a canonical hash for change detection.
"""

import ast
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Optional

from src.parsers.base import ParsedEntity

logger = logging.getLogger(__name__)

# Scoring weights (must sum to <= 1.0)
_WEIGHT_CALL_IN_DEGREE = 0.30
_WEIGHT_COMPLEXITY = 0.25
_WEIGHT_CROSS_MODULE = 0.20
_WEIGHT_PUBLIC_API = 0.15
_WEIGHT_UNUSUAL = 0.10


@dataclass
class ScoredEntity:
    entity: ParsedEntity
    score: float  # 0.0–1.0
    reasons: list[str] = field(default_factory=list)
    canonical_hash: str = ""


def score_entities(
    entities: list[ParsedEntity],
    threshold: float = 0.3,
    top_n_percent: float = 0.20,
) -> list[ScoredEntity]:
    """Score and filter entities for wiki generation.

    Uses dynamic threshold: selects entities with score > threshold OR
    top N% of the module's entities (whichever is larger).

    Args:
        entities: All parsed entities from a module.
        threshold: Minimum score to include (default 0.3).
        top_n_percent: Always include at least top N% (default 20%).

    Returns:
        Sorted list of ScoredEntity (highest score first).
    """
    if not entities:
        return []

    # Build call-in-degree map: how many other entities call each entity name
    call_targets: dict[str, int] = {}
    for entity in entities:
        for callee in entity.calls:
            call_targets[callee] = call_targets.get(callee, 0) + 1

    # Get all module names for cross-module detection
    local_names = {e.qualified_name.split(".")[-2] if "." in e.qualified_name else ""
                   for e in entities}

    scored: list[ScoredEntity] = []
    for entity in entities:
        if entity.entity_type == "module":
            continue  # skip module-level entity; it's always included

        score, reasons = _score_entity(entity, call_targets, local_names)
        h = _canonical_hash(entity)
        scored.append(ScoredEntity(entity=entity, score=score, reasons=reasons, canonical_hash=h))

    if not scored:
        return []

    # Dynamic threshold: include entities above threshold OR top N%
    scored.sort(key=lambda s: s.score, reverse=True)
    min_count = max(1, int(len(scored) * top_n_percent))
    result = [s for s in scored if s.score >= threshold]
    if len(result) < min_count:
        result = scored[:min_count]

    logger.debug("Interestingness: %d/%d entities selected", len(result), len(scored))
    return result


def _score_entity(
    entity: ParsedEntity,
    call_targets: dict[str, int],
    local_names: set[str],
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    # 1. Call-in-degree
    in_degree = call_targets.get(entity.name, 0) + call_targets.get(entity.qualified_name, 0)
    if in_degree > 0:
        degree_score = min(in_degree / 10.0, 1.0) * _WEIGHT_CALL_IN_DEGREE
        score += degree_score
        reasons.append(f"called by {in_degree} entities")

    # 2. Cyclomatic complexity proxy (branch count in signature/docstring)
    complexity = _estimate_complexity(entity)
    if complexity > 5:
        c_score = min(complexity / 20.0, 1.0) * _WEIGHT_COMPLEXITY
        score += c_score
        reasons.append(f"cyclomatic complexity ~{complexity}")

    # 3. Cross-module deps (calls outside local module)
    cross_module_calls = [
        c for c in entity.calls
        if not any(c.startswith(n) for n in local_names if n)
    ]
    if cross_module_calls:
        cm_score = min(len(cross_module_calls) / 5.0, 1.0) * _WEIGHT_CROSS_MODULE
        score += cm_score
        reasons.append(f"{len(cross_module_calls)} cross-module calls")

    # 4. Public API surface (has signature, no _ prefix, has docstring)
    if (entity.signature and
            not entity.name.startswith("_") and
            entity.entity_type in ("function", "method", "class")):
        score += _WEIGHT_PUBLIC_API
        if entity.docstring:
            reasons.append("documented public API")
        else:
            reasons.append("public API (undocumented)")

    # 5. Unusual patterns
    metadata = entity.entity_metadata or {}
    decorators = metadata.get("decorators", [])
    unusual = []
    if decorators:
        unusual.append("decorated")
    if metadata.get("is_async"):
        unusual.append("async")
    if entity.entity_type == "class" and metadata.get("bases"):
        unusual.append("inheritance")
    if unusual:
        score += _WEIGHT_UNUSUAL
        reasons.append(f"unusual: {', '.join(unusual)}")

    return min(score, 1.0), reasons


def _estimate_complexity(entity: ParsedEntity) -> int:
    """Rough cyclomatic complexity from call count + signature."""
    # Number of calls is a proxy for branch complexity
    complexity = len(entity.calls)
    # Keywords in docstring also hint at complexity
    if entity.docstring:
        doc_lower = entity.docstring.lower()
        keywords = ["if", "else", "loop", "retry", "fallback", "case", "switch", "raise", "except"]
        complexity += sum(1 for kw in keywords if kw in doc_lower)
    return complexity


def _canonical_hash(entity: ParsedEntity) -> str:
    """Stable hash for change detection — changes if signature or line range changes."""
    content = f"{entity.qualified_name}:{entity.signature}:{entity.line_start}:{entity.line_end}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]
