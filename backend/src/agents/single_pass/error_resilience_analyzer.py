"""ErrorResilienceAnalyzer — analyzes error handling patterns (1 LLM call)."""

import json
import logging

from src.agents.primitives.tools import search_code
from src.dossier.manager import DossierManager
from src.dossier.schema import ErrorResilienceProfile
from src.llm.client import chat

logger = logging.getLogger(__name__)

AGENT_NAME = "error_resilience_analyzer"


def run(repo_path: str, dossier_manager: DossierManager) -> None:
    retry_hits = search_code(repo_path, r"retry|backoff|Retry|@retry",
                             extensions=[".py", ".ts", ".js", ".go"])
    circuit_hits = search_code(repo_path, r"circuit.breaker|CircuitBreaker|hystrix",
                               extensions=[".py", ".ts", ".js", ".go", ".java"])
    bare_except = search_code(repo_path, r"except:\s*$|catch\s*\(\s*\)\s*\{",
                              extensions=[".py", ".ts", ".js"])
    global_handlers = search_code(repo_path, r"@app\.errorhandler|exception_handler|app\.use\(.*error",
                                  extensions=[".py", ".ts", ".js"])

    context = (
        f"Retry patterns: {len(retry_hits)}\n"
        f"Circuit breaker hits: {len(circuit_hits)}\n"
        f"Bare except/catch: {len(bare_except)}\n"
        f"Global error handlers: {len(global_handlers)}"
    )

    prompt = f"""Analyze error resilience from this summary:

{context}

Return JSON only:
{{
  "retry_patterns_detected": <bool>,
  "circuit_breaker_detected": <bool>,
  "global_error_handlers": ["<file>", ...],
  "silent_failures": ["<file>", ...]
}}"""

    try:
        response = chat(messages=[{"role": "user", "content": prompt}])
        data = json.loads(response)
        profile = ErrorResilienceProfile(**data)
    except Exception as exc:
        logger.warning("ErrorResilienceAnalyzer failed: %s", exc)
        profile = ErrorResilienceProfile(
            retry_patterns_detected=len(retry_hits) > 0,
            circuit_breaker_detected=len(circuit_hits) > 0,
            silent_failures=[r["file"] for r in bare_except[:5]],
        )

    dossier_manager.write_section("error_resilience", profile)
    dossier_manager.mark_agent_complete(AGENT_NAME)


