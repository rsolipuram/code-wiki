"""ObservabilityAuditor — detects logging, metrics, tracing patterns (1 LLM call)."""

import json
import logging

from src.agents.primitives.tools import search_code
from src.dossier.manager import DossierManager
from src.dossier.schema import AgentResponse, ObservabilityProfile
from src.llm.client import chat
from src.orchestrator.descriptor import AgentDescriptor

logger = logging.getLogger(__name__)

AGENT_NAME = "observability_auditor"
TAGS = ["observability", "monitoring"]


def run(repo_path: str, dossier_manager: DossierManager, compressed=None) -> None:
    log_hits = search_code(repo_path, r"logger\.|logging\.|log\.|console\.(log|error|warn)",
                           extensions=[".py", ".ts", ".js", ".go", ".java"])
    metric_hits = search_code(repo_path, r"prometheus|statsd|datadog|metrics\.|counter\.|gauge\.",
                              extensions=[".py", ".ts", ".js", ".go"])
    trace_hits = search_code(repo_path, r"opentelemetry|jaeger|zipkin|trace\.|span\.",
                             extensions=[".py", ".ts", ".js", ".go"])

    context = (
        f"Logging hits: {len(log_hits)}\n"
        f"Metrics hits: {len(metric_hits)}\n"
        f"Tracing hits: {len(trace_hits)}\n"
        f"Sample log: {log_hits[0] if log_hits else 'none'}\n"
        f"Sample metric: {metric_hits[0] if metric_hits else 'none'}"
    )

    prompt = f"""Assess observability coverage based on this search summary:

{context}

Return JSON only:
{{
  "has_logging": <bool>,
  "has_metrics": <bool>,
  "has_tracing": <bool>,
  "logging_library": "<name or null>",
  "metrics_library": "<name or null>",
  "tracing_library": "<name or null>",
  "coverage_assessment": "<good|partial|missing>"
}}"""

    try:
        response = chat(messages=[{"role": "user", "content": prompt}])
        data = json.loads(response)
        profile = ObservabilityProfile(agent_name=AGENT_NAME, **data)
    except Exception as exc:
        logger.warning("ObservabilityAuditor failed: %s", exc)
        profile = ObservabilityProfile(
            agent_name=AGENT_NAME,
            has_logging=len(log_hits) > 0,
            has_metrics=len(metric_hits) > 0,
            has_tracing=len(trace_hits) > 0,
        )

    dossier_manager.write_response(AgentResponse(
        agent_name=AGENT_NAME,
        tags=TAGS,
        confidence=profile.confidence,
        output=profile.model_dump(),
        output_type="ObservabilityProfile",
    ))
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("ObservabilityAuditor: logging=%s metrics=%s tracing=%s",
                profile.has_logging, profile.has_metrics, profile.has_tracing)


DESCRIPTOR = AgentDescriptor(
    name="observability_auditor",
    tags=TAGS,
    tier="single_pass",
    run=run,
    needs_compressed=True,
)
