"""ConflictSynthesizer — identifies contradictions between facet findings.

Per Constitution Principle II: NEVER resolves conflicts or picks winners.
Produces ConflictAnalysis objects with developer questions only.
"""

import json
import logging

from src.dossier.manager import DossierManager
from src.dossier.schema import ConflictAnalysis
from src.llm.client import chat

logger = logging.getLogger(__name__)

AGENT_NAME = "conflict_synthesizer"

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
        section_a = dossier_manager.get_section(check["facet_a"])
        section_b = dossier_manager.get_section(check["facet_b"])

        if section_a is None or section_b is None:
            continue

        # Convert to string for LLM
        def _serialize(obj):
            if obj is None:
                return "null"
            try:
                return obj.model_dump_json(indent=2)
            except AttributeError:
                return json.dumps(str(obj)[:500])

        prompt = f"""You are ConflictSynthesizer. {check['prompt_fragment']}

{check['facet_a']} findings:
{_serialize(section_a)[:800]}

{check['facet_b']} findings:
{_serialize(section_b)[:800]}

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
            dossier_manager.write_conflict(conflict)
            conflicts_written += 1
            logger.info(
                "Conflict detected: %s vs %s",
                check["facet_a"], check["facet_b"],
            )

    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("ConflictSynthesizer: %d conflicts written", conflicts_written)
