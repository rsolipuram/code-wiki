"""AuthFlowTracer — ReAct agent triggered by tag 'pattern:jwt-auth'.

Traces authentication flows: login → token issuance → validation → refresh.
"""

import logging
import time

from src.agents.primitives.tools import read_file, search_code
from src.dossier.manager import DossierManager
from src.llm.client import chat

logger = logging.getLogger(__name__)

AGENT_NAME = "auth_flow_tracer"
TRIGGER_TAGS = {"pattern:jwt-auth", "pattern:session-auth", "pattern:oauth"}
MAX_STEPS = 20
TIME_LIMIT = 180


def run(repo_path: str, dossier_manager: DossierManager) -> None:
    # Only run if triggered by a relevant tag
    if not any(dossier_manager.has_tag(tag) for tag in TRIGGER_TAGS):
        logger.info("AuthFlowTracer: no trigger tags found, skipping")
        dossier_manager.mark_agent_complete(AGENT_NAME)
        return

    start_time = time.time()
    steps = 0
    visited: set[str] = set()
    auth_flows: list[dict] = []

    auth_files = search_code(repo_path, r"login|authenticate|jwt\.sign|jwt\.verify|passport",
                             extensions=[".py", ".ts", ".js"])
    candidates = list({r["file"] for r in auth_files})

    messages = [{"role": "system", "content": (
        "You are AuthFlowTracer. Map the complete authentication flow: "
        "login endpoint → credential validation → token/session creation → middleware → protected routes. "
        "Report: AUTH_FLOW: step=<login|validate|issue|refresh|revoke> file=<path> function=<name>"
    )}]

    for file_rel in candidates[:8]:
        if steps >= MAX_STEPS or (time.time() - start_time) > TIME_LIMIT:
            break
        file_path = f"{repo_path}/{file_rel}"
        if file_path in visited:
            continue
        visited.add(file_path)
        steps += 1

        content = read_file(file_path)
        messages.append({"role": "user",
                         "content": f"Map auth flows in {file_rel}:\n```\n{content[:2000]}\n```"})
        try:
            response = chat(messages=messages)
        except Exception as exc:
            logger.warning("AuthFlowTracer LLM call failed: %s", exc)
            continue
        messages.append({"role": "assistant", "content": response})
        auth_flows.extend(_extract_auth_flows(response))
        if "STOP" in response:
            break

    extra = dossier_manager.get_section("extra") or {}
    dossier_manager.write_section("extra", {**extra, "auth_flows": auth_flows})
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("AuthFlowTracer: %d flow steps found", len(auth_flows))


def _extract_auth_flows(response: str) -> list[dict]:
    import re
    flows = []
    pattern = re.compile(r"AUTH_FLOW:\s*step=(\w+)\s+file=(\S+)\s+function=(\S+)")
    for match in pattern.finditer(response):
        flows.append({"step": match.group(1), "file": match.group(2), "function": match.group(3)})
    return flows
