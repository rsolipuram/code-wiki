"""Triage Agent — single-pass LLM call that reads RepoFingerprint and produces
an execution plan: which facet agents to run, in what order, with what budget.

The Triage Agent never loops; it makes exactly one LLM call and caches the result.
"""

import json
import logging
from typing import Any

from src.llm.client import chat
from src.recon.fingerprint import RepoFingerprint

logger = logging.getLogger(__name__)

# All available facet agents (stable registry)
_ALL_HEURISTIC_AGENTS = [
    "dependency_auditor",
    "container_analyzer",
    "ci_pipeline_analyzer",
    "iac_analyzer",
    "api_contract_extractor",
    "ownership_extractor",
    "feature_flag_mapper",
]

_ALL_REACT_AGENTS = [
    "security_sentinel",
    "data_flow_tracer",
    "auth_flow_tracer",
    "vuln_chain_tracer",
]

_ALL_SINGLE_PASS_AGENTS = [
    "architectural_classifier",
    "business_rule_extractor",
    "observability_auditor",
    "error_resilience_analyzer",
    "technical_debt_assessor",
    "performance_hotspot_scanner",
]

_TRIAGE_PROMPT = """You are the Triage Agent for a code documentation platform.
Given a repository fingerprint, decide which analysis agents to activate and in what priority order.

Repository fingerprint:
{fingerprint_json}

Return a JSON object (NO markdown, NO explanation outside JSON):
{{
  "heuristic_agents": ["agent_name", ...],
  "react_agents": ["agent_name", ...],
  "single_pass_agents": ["agent_name", ...],
  "rationale": "brief explanation of choices",
  "estimated_budget_llm_calls": <integer>
}}

Available agents:
Heuristic (zero LLM): {heuristic_list}
ReAct (iterative LLM): {react_list}
Single-pass (1 LLM call each): {single_pass_list}

Rules:
- Always include all heuristic agents (they're free)
- Include security_sentinel if any web framework or auth libraries detected
- Include auth_flow_tracer only if pattern:jwt-auth or similar detected
- Prioritize accuracy over speed for react agents
- Return ONLY valid JSON
"""


def run(fingerprint: RepoFingerprint) -> dict[str, Any]:
    """Produce an execution plan from a RepoFingerprint.

    Args:
        fingerprint: The RepoFingerprint from Layer 0.

    Returns:
        Dict with keys: heuristic_agents, react_agents, single_pass_agents,
        rationale, estimated_budget_llm_calls.
        Falls back to full agent set if LLM call fails.
    """
    prompt = _TRIAGE_PROMPT.format(
        fingerprint_json=json.dumps(fingerprint.to_dict(), indent=2),
        heuristic_list=", ".join(_ALL_HEURISTIC_AGENTS),
        react_list=", ".join(_ALL_REACT_AGENTS),
        single_pass_list=", ".join(_ALL_SINGLE_PASS_AGENTS),
    )

    try:
        response = chat(
            messages=[{"role": "user", "content": prompt}],
            cache_ttl=3600,
        )
        plan = json.loads(response)
        # Validate required keys
        for key in ("heuristic_agents", "react_agents", "single_pass_agents"):
            if key not in plan:
                raise ValueError(f"Missing key {key!r} in triage response")
        logger.info("Triage plan: %s", plan.get("rationale", ""))
        return plan
    except Exception as exc:
        logger.warning("Triage LLM call failed (%s) — using full agent set", exc)
        return {
            "heuristic_agents": _ALL_HEURISTIC_AGENTS,
            "react_agents": _ALL_REACT_AGENTS,
            "single_pass_agents": _ALL_SINGLE_PASS_AGENTS,
            "rationale": "Fallback: LLM unavailable, running all agents",
            "estimated_budget_llm_calls": len(_ALL_REACT_AGENTS) + len(_ALL_SINGLE_PASS_AGENTS),
        }
