"""ConflictSynthesizer — identifies contradictions between facet findings.

Per Constitution Principle II: NEVER resolves conflicts or picks winners.
Produces ConflictAnalysis objects with developer questions only.
"""

import json
import logging

from src.dossier.manager import DossierManager
from src.dossier.schema import AgentResponse, ConflictAnalysis
from src.llm.client import chat

logger = logging.getLogger(__name__)

AGENT_NAME = "conflict_synthesizer"
TAGS = ["conflict", "cross-cutting"]

_CONFLICT_CHECKS = [
    {
        "facet_a": "architecture",
        "facet_b": "dependencies",
        "prompt_fragment": "Check if the architectural style claimed by ArchitecturalClassifier is consistent with the dependency list.",
    },
    {
        "facet_a": "security",
        "facet_b": "ci_pipeline",
        "prompt_fragment": "Check if security findings are contradicted by CI pipeline security steps (e.g., SAST/DAST steps).",
    },
    {
        "facet_a": "observability",
        "facet_b": "error_resilience",
        "prompt_fragment": "Check if the observability profile matches the error resilience profile (e.g., good observability but many silent failures).",
    },
]


def run(dossier_manager: DossierManager) -> None:
    """Identify contradictions between facet findings."""
    conflicts_written = 0

    for check in _CONFLICT_CHECKS:
        responses_a = dossier_manager.dossier.by_tag(check["facet_a"])
        responses_b = dossier_manager.dossier.by_tag(check["facet_b"])

        if not responses_a or not responses_b:
            continue

        def _serialize_responses(responses):
            parts = []
            for r in responses[:3]:
                parts.append(json.dumps(r.output, default=str)[:400])
            return "\n".join(parts)

        prompt = f"""You are ConflictSynthesizer. {check['prompt_fragment']}

{check['facet_a']} findings:
{_serialize_responses(responses_a)[:800]}

{check['facet_b']} findings:
{_serialize_responses(responses_b)[:800]}

IMPORTANT RULES:
- Do NOT pick a winner or say one finding is "correct"
- Do NOT resolve the conflict
- Do generate neutral developer questions

If you detect a genuine contradiction, return JSON:
{{
  "conflict_detected": true,
  "finding_a": "<what facet A claims>",
  "finding_b": "<what facet B claims>",
  "why_both_coexist": "<neutral explanation>",
  "developer_questions": ["<question>", ...]
}}

If no contradiction, return:
{{"conflict_detected": false}}"""

        try:
            response = chat(messages=[{"role": "user", "content": prompt}])
            data = json.loads(response)
        except Exception as exc:
            logger.debug("ConflictSynthesizer check skipped (%s): %s", check["facet_a"], exc)
            continue

        if data.get("conflict_detected"):
            conflict = ConflictAnalysis(
                facet_a=check["facet_a"],
                finding_a=data.get("finding_a", ""),
                facet_b=check["facet_b"],
                finding_b=data.get("finding_b", ""),
                why_both_coexist=data.get("why_both_coexist", ""),
                developer_questions=data.get("developer_questions", []),
            )
            dossier_manager.write_response(AgentResponse(
                agent_name=AGENT_NAME,
                tags=TAGS,
                output=conflict.model_dump(),
                output_type="ConflictAnalysis",
            ))
            conflicts_written += 1
            logger.info(
                "Conflict detected: %s vs %s",
                check["facet_a"], check["facet_b"],
            )

    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("ConflictSynthesizer: %d conflicts written", conflicts_written)
