"""IaCAnalyzer — identifies IaC files (Terraform, K8s, Helm) with zero LLM calls."""

import logging
from pathlib import Path

from src.dossier.manager import DossierManager
from src.dossier.schema import IaCAnalysis, IaCResource

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

    # Determine primary provider (first detected tool wins)
    primary_provider = next(iter(findings), "")

    # Build IaCResource list from discovered files
    resources: list[IaCResource] = []
    for tool, files in findings.items():
        for file_path in files:
            resources.append(IaCResource(
                resource_type="file",
                name=file_path,
                provider=tool,
            ))

    dossier_manager.write_section(
        "iac",
        IaCAnalysis(
            agent_name=AGENT_NAME,
            provider=primary_provider,
            resources=resources,
        ),
    )
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("IaCAnalyzer: detected tools %s", list(findings.keys()))
