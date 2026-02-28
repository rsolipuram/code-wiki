"""TAG_TRIGGERS registry — maps agent-emitted tags to downstream agents to invoke.

This is the static routing table for the orchestrator.
Tags are strings emitted by facet agents; triggers are agent names to invoke next.

No LLM calls in this module — all routing is deterministic.
"""

# Maps tag → list of agent names to invoke when that tag is emitted
TAG_TRIGGERS: dict[str, list[str]] = {
    # Security-related triggers
    "risk:jwt-without-rotation": ["auth_flow_tracer"],
    "risk:jwt-expired": ["auth_flow_tracer"],
    "pattern:jwt-auth": ["auth_flow_tracer"],
    "pattern:session-auth": ["auth_flow_tracer"],
    "pattern:oauth": ["auth_flow_tracer"],
    "risk:sql-injection": ["vuln_chain_tracer"],
    "risk:xss": ["vuln_chain_tracer"],
    "risk:command-injection": ["vuln_chain_tracer"],
    "risk:path-traversal": ["vuln_chain_tracer"],
    "risk:secret-exposure": ["security_sentinel"],  # re-run sentinel on secrets

    # Dependency-related triggers
    "risk:critical-vulnerability": ["dependency_auditor"],

    # Architecture-related triggers
    "pattern:microservices": ["container_analyzer"],
    "pattern:event-driven": ["data_flow_tracer"],

    # Observability triggers
    "missing:logging": ["observability_auditor"],
    "missing:tracing": ["observability_auditor"],
}


def get_triggered_agents(tag: str) -> list[str]:
    """Return the list of agents to invoke for a given tag.

    Args:
        tag: An emitted tag string (e.g. "risk:sql-injection").

    Returns:
        List of agent names to trigger. Empty list if tag unknown.
    """
    return TAG_TRIGGERS.get(tag, [])


def get_all_triggered_agents(tags: list[str]) -> list[str]:
    """Return deduplicated list of agents triggered by any of the given tags."""
    triggered: set[str] = set()
    for tag in tags:
        triggered.update(get_triggered_agents(tag))
    return sorted(triggered)
