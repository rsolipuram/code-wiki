"""Agent descriptors — self-describing metadata for each facet agent.

Each agent exports a module-level DESCRIPTOR that tells the orchestrator
everything it needs to know: name, tier, tags, resource requirements, and
the callable entry point. The orchestrator discovers agents by collecting
DESCRIPTOR from each module — no hardcoded dicts needed.
"""

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class AgentDescriptor:
    """Self-describing metadata exported by every facet agent."""

    name: str
    tags: list[str]
    tier: str  # "heuristic" | "react" | "single_pass" | "synthesis"
    run: Callable  # the module's run() function
    needs_fingerprint: bool = False
    needs_compressed: bool = False
    timeout: int = 300
    optional: bool = False
