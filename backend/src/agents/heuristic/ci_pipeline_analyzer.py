"""CIPipelineAnalyzer — parses GitHub Actions workflows and Jenkinsfiles (zero LLM)."""

import logging
import re
from pathlib import Path

import yaml

from src.dossier.manager import DossierManager
from src.dossier.schema import CIJob, CIPipeline, CIStep

logger = logging.getLogger(__name__)

AGENT_NAME = "ci_pipeline_analyzer"


def run(repo_path: str, dossier_manager: DossierManager) -> None:
    root = Path(repo_path)

    pipeline = _parse_github_actions(root)
    if not pipeline:
        pipeline = _parse_jenkinsfile(root)
    if not pipeline:
        pipeline = CIPipeline(provider="none")

    dossier_manager.write_section("ci_pipeline", pipeline)
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("CIPipelineAnalyzer: provider=%s, jobs=%d", pipeline.provider, len(pipeline.jobs))


def _parse_github_actions(root: Path) -> CIPipeline | None:
    workflows_dir = root / ".github" / "workflows"
    if not workflows_dir.exists():
        return None

    jobs: list[CIJob] = []
    triggers: list[str] = []
    has_tests = has_deploy = has_lint = False

    for workflow_file in workflows_dir.glob("*.yml"):
        try:
            data = yaml.safe_load(workflow_file.read_text()) or {}
        except Exception:
            continue

        on = data.get("on") or data.get(True) or {}
        if isinstance(on, dict):
            triggers.extend(on.keys())
        elif isinstance(on, list):
            triggers.extend(on)
        elif isinstance(on, str):
            triggers.append(on)

        for job_name, job_data in (data.get("jobs") or {}).items():
            if not isinstance(job_data, dict):
                continue
            steps: list[CIStep] = []
            for step in job_data.get("steps") or []:
                step_name = step.get("name", "")
                step_uses = step.get("uses", "")
                step_run = step.get("run", "")
                steps.append(CIStep(name=step_name, command=step_run or None, uses=step_uses or None))
                lower = (step_name + step_run).lower()
                if any(kw in lower for kw in ["test", "pytest", "jest", "mocha"]):
                    has_tests = True
                if any(kw in lower for kw in ["deploy", "publish", "release"]):
                    has_deploy = True
                if any(kw in lower for kw in ["lint", "eslint", "ruff", "flake8"]):
                    has_lint = True
            jobs.append(CIJob(
                name=job_name,
                runner=job_data.get("runs-on"),
                steps=steps,
            ))

    return CIPipeline(
        provider="github_actions",
        triggers=list(set(triggers)),
        jobs=jobs,
        has_tests=has_tests,
        has_deploy=has_deploy,
        has_lint=has_lint,
    )


def _parse_jenkinsfile(root: Path) -> CIPipeline | None:
    jenkins = root / "Jenkinsfile"
    if not jenkins.exists():
        return None
    try:
        content = jenkins.read_text()
        stage_names = re.findall(r"stage\s*\(\s*['\"](.+?)['\"]\s*\)", content)
        steps = [CIStep(name=s) for s in stage_names]
        has_tests = any("test" in s.lower() for s in stage_names)
        has_deploy = any("deploy" in s.lower() for s in stage_names)
        return CIPipeline(
            provider="jenkins",
            triggers=["push"],
            jobs=[CIJob(name="pipeline", steps=steps)],
            has_tests=has_tests,
            has_deploy=has_deploy,
        )
    except OSError:
        return None
