"""BusinessRuleExtractor — extracts business rules and domain entities (1 LLM call)."""

import json
import logging
from pathlib import Path
from typing import Optional

from src.agents.primitives.tools import search_code
from src.dossier.manager import DossierManager
from src.dossier.schema import AgentResponse, BusinessRule, DomainModel
from src.llm.client import chat

logger = logging.getLogger(__name__)

AGENT_NAME = "business_rule_extractor"
TAGS = ["domain", "business-rules"]


def run(repo_path: str, dossier_manager: DossierManager, compressed=None) -> None:
    # Build candidate file list: prefer key_entities from compressed if available
    if compressed is not None and compressed.key_entities:
        # Extract unique file paths from top-scored entities (classes, interfaces, models)
        seen: set[str] = set()
        candidate_files: list[str] = []
        for entity in compressed.key_entities:
            f = entity.get("file_path", "")
            if f and f not in seen:
                seen.add(f)
                candidate_files.append(f)
        samples = []
        for rel_path in candidate_files[:15]:
            file_path = Path(repo_path) / rel_path
            try:
                content = file_path.read_text(errors="replace")[:1500]
                # Prefer LLM summary if available, prepend it for context
                summary = compressed.file_summaries.get(rel_path)
                header = f"[Summary: {summary.summary}]\n" if summary else ""
                samples.append(f"--- {rel_path} ---\n{header}{content}")
            except OSError:
                pass
    else:
        # Fallback: regex search
        domain_files = search_code(repo_path, r"class|interface|struct|type\s+\w+",
                                   extensions=[".py", ".ts", ".go", ".java"])
        samples = []
        for result in domain_files[:15]:
            file_path = Path(repo_path) / result["file"]
            try:
                content = file_path.read_text(errors="replace")[:1500]
                samples.append(f"--- {result['file']} ---\n{content}")
            except OSError:
                pass

    if not samples:
        empty_model = DomainModel(agent_name=AGENT_NAME)
        dossier_manager.write_response(AgentResponse(
            agent_name=AGENT_NAME,
            tags=TAGS,
            confidence=empty_model.confidence,
            output=empty_model.model_dump(),
            output_type="DomainModel",
        ))
        dossier_manager.mark_agent_complete(AGENT_NAME)
        return

    prompt = f"""Extract business rules and domain entities from these code samples.

{chr(10).join(samples[:5])}

Return JSON only:
{{
  "entities": ["<EntityName>", ...],
  "business_rules": [
    {{"description": "<rule>", "related_files": ["<file>"], "source": "docstring|comment|inferred"}},
    ...
  ],
  "ubiquitous_language": ["<term>", ...]
}}"""

    try:
        response = chat(messages=[{"role": "user", "content": prompt}])
        data = json.loads(response)
        rules = [BusinessRule(**r) for r in data.get("business_rules", [])]
        model = DomainModel(
            agent_name=AGENT_NAME,
            entities=data.get("entities", []),
            business_rules=rules,
            ubiquitous_language=data.get("ubiquitous_language", []),
        )
    except Exception as exc:
        logger.warning("BusinessRuleExtractor failed: %s", exc)
        model = DomainModel(agent_name=AGENT_NAME)

    dossier_manager.write_response(AgentResponse(
        agent_name=AGENT_NAME,
        tags=TAGS,
        confidence=model.confidence,
        output=model.model_dump(),
        output_type="DomainModel",
    ))
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("BusinessRuleExtractor: %d entities, %d rules",
                len(model.entities), len(model.business_rules))
