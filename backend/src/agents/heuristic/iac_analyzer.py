"""IaCAnalyzer — identifies IaC files (Terraform, K8s, Helm) with zero LLM calls."""

import logging
from pathlib import Path

from src.dossier.manager import DossierManager

logger = logging.getLogger(__name__)

AGENT_NAME = "iac_analyzer"

_IaC_PATTERNS = {
    "terraform": ["*.tf", "*.tfvars"],
    "kubernetes": ["*.k8s.yaml", "kubernetes/**/*.yaml", "k8s/**/*.yaml", "deploy/**/*.yaml"],
    "helm": ["Chart.yaml", "helm/**"],
    "ansible": ["playbook*.yml", "ansible/**/*.yml"],
    "pulumi": ["Pulumi.yaml"],
    "cdk": ["cdk.json"],
}


def run(repo_path: str, dossier_manager: DossierManager) -> None:
    root = Path(repo_path)
    findings: dict[str, list[str]] = {}

    for tool, patterns in _IaC_PATTERNS.items():
        matched: list[str] = []
        for pattern in patterns:
            for p in root.rglob(pattern.replace("**", "*")):
                if p.is_file():
                    matched.append(str(p.relative_to(root)))
        if matched:
            findings[tool] = matched

    # Store in Dossier extra field (no dedicated schema section for IaC yet)
    dossier_manager.write_section(
        "extra",
        {**dossier_manager.get_section("extra"), "iac": findings},
    )
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("IaCAnalyzer: detected tools %s", list(findings.keys()))
