"""ArchitecturalClassifier — single-pass LLM agent classifying system architecture."""

import json
import logging

from src.dossier.manager import DossierManager
from src.dossier.schema import AgentResponse, ArchitectureStyle
from src.llm.client import chat
from src.recon.fingerprint import RepoFingerprint

logger = logging.getLogger(__name__)

AGENT_NAME = "architectural_classifier"
TAGS = ["architecture", "design-patterns"]

_PROMPT = """Classify the architecture of a software system based on the repository fingerprint and entity summary.

Fingerprint: {fingerprint}
Top-level directories: {directories}

Return JSON only (no markdown):
{{
  "primary_style": "<monolith|microservices|event-driven|serverless|hybrid>",
  "confidence": <0.0-1.0>,
  "patterns_detected": ["<pattern>", ...],
  "layers": ["<layer>", ...],
  "rationale": "<brief explanation>"
}}
"""


def run(repo_path: str, dossier_manager: DossierManager, fingerprint: RepoFingerprint, compressed=None) -> None:
    import os
    try:
        dirs = [d for d in os.listdir(repo_path) if os.path.isdir(os.path.join(repo_path, d))
                and not d.startswith(".")][:20]
    except OSError:
        dirs = []

    prompt = _PROMPT.format(
        fingerprint=json.dumps(fingerprint.to_dict()),
        directories=dirs,
    )

    try:
        response = chat(
            messages=[{"role": "user", "content": prompt}],
            cache_ttl=3600,
        )
        data = json.loads(response)
        style = ArchitectureStyle(agent_name=AGENT_NAME, **data)
    except Exception as exc:
        logger.warning("ArchitecturalClassifier failed: %s", exc)
        style = ArchitectureStyle(
            agent_name=AGENT_NAME,
            primary_style=fingerprint.system_type,
            confidence=0.3,
            rationale="Fallback from RepoFingerprint system_type",
        )

    dossier_manager.write_response(AgentResponse(
        agent_name=AGENT_NAME,
        tags=TAGS,
        confidence=style.confidence,
        output=style.model_dump(),
        output_type="ArchitectureStyle",
    ))
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("ArchitecturalClassifier: %s (%.2f)", style.primary_style, style.confidence)
