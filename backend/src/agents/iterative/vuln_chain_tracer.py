"""VulnChainTracer — ReAct agent triggered by 'risk:sql-injection' or similar tags.

Traces vulnerability chains: tainted input → propagation → sink.
"""

import logging
import time

from src.agents.primitives.tools import read_file, search_code
from src.dossier.manager import DossierManager
from src.dossier.schema import AgentResponse, SecurityFinding, Severity
from src.llm.client import chat

logger = logging.getLogger(__name__)

AGENT_NAME = "vuln_chain_tracer"
TAGS = ["security", "vulnerability"]
TRIGGER_TAGS = {"risk:sql-injection", "risk:xss", "risk:command-injection", "risk:path-traversal"}
MAX_STEPS = 15
TIME_LIMIT = 150


def run(repo_path: str, dossier_manager: DossierManager, compressed=None) -> None:
    triggered_risks = [tag for tag in TRIGGER_TAGS if dossier_manager.has_tag(tag)]
    if not triggered_risks:
        logger.info("VulnChainTracer: no trigger tags, skipping")
        dossier_manager.mark_agent_complete(AGENT_NAME)
        return

    start_time = time.time()
    steps = 0

    for risk_tag in triggered_risks[:2]:  # cap at 2 risk types
        risk_type = risk_tag.split(":")[1]
        files = search_code(repo_path, rf"{risk_type.replace('-', '|')}",
                            extensions=[".py", ".ts", ".js"])
        candidates = list({r["file"] for r in files})

        for file_rel in candidates[:5]:
            if steps >= MAX_STEPS or (time.time() - start_time) > TIME_LIMIT:
                break
            steps += 1
            content = read_file(f"{repo_path}/{file_rel}")
            try:
                response = chat(messages=[
                    {"role": "system", "content": (
                        f"Trace {risk_type} vulnerability chain in this file. "
                        "Report: VULN_CHAIN: source=<var/param> propagation=<desc> sink=<file:line>"
                    )},
                    {"role": "user",
                     "content": f"File: {file_rel}\n```\n{content[:2000]}\n```"},
                ])
            except Exception as exc:
                logger.warning("VulnChainTracer LLM call failed: %s", exc)
                continue

            # Write confirmed chains as security findings
            if "VULN_CHAIN" in response:
                finding = SecurityFinding(
                    type=f"{risk_type}-chain",
                    severity=Severity.HIGH,
                    related_files=[file_rel],
                    related_modules=[],
                    description=f"Vulnerability chain detected in {file_rel}: {response[:200]}",
                    evidence_lines=[file_rel],
                    tags=[risk_tag],
                )
                dossier_manager.write_response(AgentResponse(
                    agent_name=AGENT_NAME,
                    tags=TAGS + [risk_tag],
                    confidence=1.0,
                    output=finding.model_dump(),
                    output_type="SecurityFinding",
                ))

    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("VulnChainTracer: completed in %d steps", steps)
