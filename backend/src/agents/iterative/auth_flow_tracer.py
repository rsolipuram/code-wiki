"""AuthFlowTracer — ReAct agent triggered by tag 'pattern:jwt-auth'.

Traces authentication flows: login → token issuance → validation → refresh.
"""

import logging
import time
from typing import Optional

from src.agents.primitives.tools import read_file, search_code
from src.dossier.manager import DossierManager
from src.dossier.schema import AgentResponse, AuthFlow, AuthFlowAnalysis
from src.llm.client import chat
from src.orchestrator.descriptor import AgentDescriptor

logger = logging.getLogger(__name__)

AGENT_NAME = "auth_flow_tracer"
TAGS = ["auth", "security", "identity"]
TRIGGER_TAGS = {"pattern:jwt-auth", "pattern:session-auth", "pattern:oauth"}
MAX_STEPS = 20
TIME_LIMIT = 180

_AUTH_KEYWORDS = {"login", "authenticate", "jwt", "token", "session", "oauth", "passport", "bearer"}


def run(repo_path: str, dossier_manager: DossierManager, compressed=None) -> None:
    start_time = time.time()
    steps = 0
    visited: set[str] = set()
    raw_flows: list[dict] = []

    # Use compressed file_summaries + import_graph to pre-identify auth files
    if compressed is not None and compressed.file_summaries:
        candidates: list[str] = []
        for rel_path, summary in compressed.file_summaries.items():
            text = (summary.summary or "").lower()
            if any(kw in text for kw in _AUTH_KEYWORDS):
                candidates.append(rel_path)
        # Also scan import_graph context for auth-related paths
        if not candidates and compressed.import_graph_summary:
            # Fall through to regex search below
            candidates = []
        logger.info("AuthFlowTracer: %d candidate files from compressed summaries", len(candidates))
    else:
        candidates = []

    if not candidates:
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
        raw_flows.extend(_extract_auth_flows(response))
        if "STOP" in response:
            break

    # Infer auth patterns from found files and LLM analysis
    detected_patterns: list[AuthFlow] = []
    if raw_flows:
        # Derive pattern from step names found in the flow
        steps_seen = {f.get("step", "") for f in raw_flows}
        if any(s in steps_seen for s in ("issue", "validate", "refresh", "revoke")):
            detected_patterns.append(AuthFlow(pattern="jwt"))
        elif steps_seen:
            detected_patterns.append(AuthFlow(pattern="session"))
    elif candidates:
        # Files exist but LLM found no structured flows — still record an unknown pattern
        detected_patterns.append(AuthFlow(pattern="unknown"))

    analysis = AuthFlowAnalysis(
        agent_name=AGENT_NAME,
        flows=detected_patterns,
    )
    dossier_manager.write_response(AgentResponse(
        agent_name=AGENT_NAME,
        tags=TAGS,
        confidence=1.0,
        output=analysis.model_dump(),
        output_type="AuthFlowAnalysis",
    ))
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("AuthFlowTracer: %d flow steps found", len(raw_flows))


def _extract_auth_flows(response: str) -> list[dict]:
    import re
    flows = []
    pattern = re.compile(r"AUTH_FLOW:\s*step=(\w+)\s+file=(\S+)\s+function=(\S+)")
    for match in pattern.finditer(response):
        flows.append({"step": match.group(1), "file": match.group(2), "function": match.group(3)})
    return flows


DESCRIPTOR = AgentDescriptor(
    name="auth_flow_tracer",
    tags=TAGS,
    tier="react",
    run=run,
    needs_compressed=True,
)
