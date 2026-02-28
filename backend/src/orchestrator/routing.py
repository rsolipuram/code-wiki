"""Heuristic routing functions for the LangGraph orchestrator.

All routing is deterministic — no LLM calls in this module.
These are pure Python conditional edges consumed by StateGraph.
"""

from typing import Literal

from src.dossier.schema import Dossier
from src.orchestrator.tag_triggers import get_all_triggered_agents


def route_after_heuristic(dossier: Dossier) -> str:
    """After all heuristic agents complete, always proceed to ReAct agents."""
    return "react_layer"


def route_after_react(dossier: Dossier) -> str:
    """After ReAct agents, check if any new tags triggered more agents.

    Returns:
        'tag_triggered_agents' if new agents need to run, else 'single_pass_layer'
    """
    triggered = get_all_triggered_agents(dossier.emitted_tags)
    # Filter to agents not yet completed
    pending = [a for a in triggered if a not in dossier.agents_completed]
    return "tag_triggered_agents" if pending else "single_pass_layer"


def route_after_single_pass(dossier: Dossier) -> str:
    """After single-pass agents, always proceed to conflict synthesis."""
    return "conflict_synthesizer"


def route_after_conflict(dossier: Dossier) -> str:
    """After conflict synthesis, proceed to wiki generation."""
    return "wiki_generation"


def should_run_security(dossier: Dossier) -> bool:
    """Heuristic: run SecuritySentinel if web framework detected."""
    if dossier.dependencies:
        pkg_names = [p.name.lower() for p in dossier.dependencies.packages]
        web_frameworks = {"fastapi", "flask", "django", "express", "koa", "nestjs", "spring"}
        return bool(set(pkg_names) & web_frameworks)
    return True  # run by default if no dep info


def pending_tag_agents(dossier: Dossier) -> list[str]:
    """Return list of tag-triggered agents not yet completed."""
    triggered = get_all_triggered_agents(dossier.emitted_tags)
    return [a for a in triggered if a not in dossier.agents_completed]
