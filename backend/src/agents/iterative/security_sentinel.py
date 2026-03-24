"""SecuritySentinel — ReAct agent that traces auth flows and detects security risks.

Uses LangGraph's create_react_agent with hard safeguards:
- MAX_STEPS = 30 iterations
- TIME_LIMIT = 300 seconds
- Visited-set tracking (no re-reading files)
- Convergence stop (3 consecutive no-new-findings)
- Progressive Dossier writes (mid-loop, not just at end)
"""

import logging
import time
import uuid
from typing import Any

from src.agents.primitives.tools import read_file, search_code
from src.dossier.manager import DossierManager
from src.dossier.schema import AgentResponse, SecurityFinding, Severity
from src.llm.client import chat

logger = logging.getLogger(__name__)

AGENT_NAME = "security_sentinel"
TAGS = ["security", "risk"]
MAX_STEPS = 30
TIME_LIMIT = 300  # seconds
CONVERGENCE_PATIENCE = 3  # consecutive no-new-findings before stopping

_SECURITY_KEYWORDS = {
    "auth", "login", "password", "jwt", "token", "session", "oauth",
    "sql", "query", "injection", "secret", "key", "crypto", "hash",
    "cors", "csrf", "xss", "deserializ", "pickle", "eval", "exec",
}

_SYSTEM_PROMPT = """You are SecuritySentinel, a specialist security analyst for code repositories.

Your goal: identify authentication vulnerabilities, injection risks, secret exposure, and insecure patterns.

For each file you analyze, look for:
1. JWT usage without rotation or expiry checks
2. SQL/NoSQL injection risks (string concatenation in queries)
3. Hardcoded secrets, API keys, or passwords
4. Missing input validation
5. Insecure deserialization
6. CORS misconfigurations
7. Missing rate limiting on auth endpoints
8. Weak cryptography (MD5, SHA1 for passwords)

After each file analysis, report findings immediately. Format each finding as:
FINDING: type=<type> severity=<critical|high|medium|low> file=<path>:<line> description=<description>

When you've covered all relevant files or have enough evidence, say STOP.
"""


def run(repo_path: str, dossier_manager: DossierManager, compressed=None) -> None:
    """Execute the SecuritySentinel ReAct loop."""
    start_time = time.time()
    steps = 0
    visited: set[str] = set()
    consecutive_no_findings = 0
    total_findings = 0

    # Use compressed file_summaries to pre-identify risky files
    if compressed is not None and compressed.file_summaries:
        candidate_files: list[str] = []
        for rel_path, summary in compressed.file_summaries.items():
            text = (summary.summary or "").lower()
            if any(kw in text for kw in _SECURITY_KEYWORDS):
                candidate_files.append(rel_path)
        logger.info("SecuritySentinel: %d candidate files from compressed summaries", len(candidate_files))
    else:
        candidate_files = []

    if not candidate_files:
        # Fallback: regex search
        auth_files = search_code(repo_path, r"auth|login|password|jwt|token|session|oauth",
                                 extensions=[".py", ".ts", ".tsx", ".js", ".jsx"])
        security_files = search_code(repo_path, r"sql|query|execute|cursor|db\.run",
                                     extensions=[".py", ".ts", ".js"])
        candidate_files = list({r["file"] for r in auth_files + security_files})

    if not candidate_files:
        logger.info("SecuritySentinel: no candidate files found")
        dossier_manager.mark_agent_complete(AGENT_NAME)
        return

    messages: list[dict[str, str]] = [{"role": "system", "content": _SYSTEM_PROMPT}]

    for file_rel in candidate_files:
        if steps >= MAX_STEPS or (time.time() - start_time) > TIME_LIMIT:
            logger.warning("SecuritySentinel: hit limit at step %d", steps)
            break

        file_path = f"{repo_path}/{file_rel}"
        if file_path in visited:
            continue
        visited.add(file_path)
        steps += 1

        content = read_file(file_path)
        messages.append({
            "role": "user",
            "content": f"Analyze this file for security issues:\n\nFile: {file_rel}\n\n```\n{content[:3000]}\n```"
        })

        try:
            response = chat(messages=messages)
        except Exception as exc:
            logger.warning("SecuritySentinel LLM call failed: %s", exc)
            continue

        messages.append({"role": "assistant", "content": response})

        # Extract findings from response
        findings_found = _extract_findings(response, file_path, dossier_manager)
        if findings_found == 0:
            consecutive_no_findings += 1
        else:
            total_findings += findings_found
            consecutive_no_findings = 0

        if consecutive_no_findings >= CONVERGENCE_PATIENCE:
            logger.info("SecuritySentinel: converged after %d steps", steps)
            break

        if "STOP" in response:
            break

    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info(
        "SecuritySentinel: %d steps, %d findings, %.1fs",
        steps, total_findings, time.time() - start_time,
    )


def _extract_findings(response: str, file_path: str, dossier_manager: DossierManager) -> int:
    """Parse FINDING: lines from agent response and write to Dossier."""
    import re
    count = 0
    pattern = re.compile(
        r"FINDING:\s*type=([\w\-]+)\s+severity=(\w+)\s+file=(\S+)\s+description=(.+)"
    )
    for match in pattern.finditer(response):
        finding_type = match.group(1)
        severity_str = match.group(2).lower()
        evidence_file = match.group(3)
        description = match.group(4).strip()

        try:
            severity = Severity(severity_str)
        except ValueError:
            severity = Severity.MEDIUM

        finding = SecurityFinding(
            type=finding_type,
            severity=severity,
            related_files=[evidence_file],
            related_modules=[],
            description=description,
            evidence_lines=[evidence_file],
            tags=[f"risk:{finding_type}"],
        )
        dossier_manager.write_response(AgentResponse(
            agent_name=AGENT_NAME,
            tags=TAGS + finding.tags,
            confidence=1.0,
            output=finding.model_dump(),
            output_type="SecurityFinding",
        ))
        count += 1
    return count
