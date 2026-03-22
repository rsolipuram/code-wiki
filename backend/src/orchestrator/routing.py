"""Heuristic routing functions for the LangGraph orchestrator.

All routing is deterministic — no LLM calls in this module.
These are pure Python conditional edges consumed by StateGraph.
"""

from src.dossier.schema import Dossier


def route_after_heuristic(dossier: Dossier) -> str:
    """After all heuristic agents complete, always proceed to ReAct agents."""
    return "react_layer"


def route_after_react(dossier: Dossier) -> str:
    """After ReAct agents, proceed directly to single-pass layer."""
    return "single_pass_layer"


def route_after_single_pass(dossier: Dossier) -> str:
    """After single-pass agents, always proceed to conflict synthesis."""
    return "conflict_synthesizer"


def route_after_conflict(dossier: Dossier) -> str:
    """After conflict synthesis, proceed to wiki generation."""
    return "wiki_generation"


def should_run_security(dossier: Dossier) -> bool:
    """Heuristic: run SecuritySentinel if web framework detected."""
    deps = dossier.sections.get("dependencies")
    if deps is not None and hasattr(deps, "packages"):
        pkg_names = [p.name.lower() for p in deps.packages]
        web_frameworks = {"fastapi", "flask", "django", "express", "koa", "nestjs", "spring"}
        return bool(set(pkg_names) & web_frameworks)
    return True  # run by default if no dep info
