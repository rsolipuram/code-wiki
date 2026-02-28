"""BusinessRuleExtractor — extracts business rules and domain entities (1 LLM call)."""

import json
import logging
from pathlib import Path

from src.agents.primitives.tools import search_code
from src.dossier.manager import DossierManager
from src.dossier.schema import BusinessRule, DomainModel
from src.llm.client import chat

logger = logging.getLogger(__name__)

AGENT_NAME = "business_rule_extractor"


def run(repo_path: str, dossier_manager: DossierManager) -> None:
    # Collect docstrings and comments from domain-ish files
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
        dossier_manager.write_section("domain_model", DomainModel())
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
            entities=data.get("entities", []),
            business_rules=rules,
            ubiquitous_language=data.get("ubiquitous_language", []),
        )
    except Exception as exc:
        logger.warning("BusinessRuleExtractor failed: %s", exc)
        model = DomainModel()

    dossier_manager.write_section("domain_model", model)
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("BusinessRuleExtractor: %d entities, %d rules",
                len(model.entities), len(model.business_rules))
