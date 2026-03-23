"""DataFlowTracer — ReAct agent that traces data transformations from entry points.

Applies the same termination safeguards as SecuritySentinel.
Writes to Dossier sections['data_flow'].
"""

import logging
import time
from typing import Optional

from src.agents.primitives.tools import read_file, search_code
from src.dossier.manager import DossierManager
from src.dossier.schema import DataFlowAnalysis, DataFlowEdge
from src.llm.client import chat

logger = logging.getLogger(__name__)

AGENT_NAME = "data_flow_tracer"
MAX_STEPS = 25
TIME_LIMIT = 240

_SYSTEM_PROMPT = """You are DataFlowTracer, analyzing how data moves through a codebase.

Trace: entry points (API handlers, CLI args, file reads) → transformations → storage/output.

For each data flow found, report:
FLOW: entry=<file:fn> transform=<description> destination=<file or type>

Say STOP when you have mapped the main data flows.
"""

_ENTRY_POINT_KEYWORDS = {
    "route", "handler", "endpoint", "controller", "api", "request", "response",
    "handle", "process", "dispatch", "receive",
}


def run(repo_path: str, dossier_manager: DossierManager, compressed=None) -> None:
    start_time = time.time()
    steps = 0
    visited: set[str] = set()
    raw_flows: list[dict] = []

    # Use compressed call_graph_summary + file_summaries to locate entry points
    if compressed is not None and compressed.file_summaries:
        candidate_files: list[str] = []
        for rel_path, summary in compressed.file_summaries.items():
            text = (summary.summary or "").lower()
            if any(kw in text for kw in _ENTRY_POINT_KEYWORDS):
                candidate_files.append(rel_path)
        logger.info("DataFlowTracer: %d candidate files from compressed summaries", len(candidate_files))
    else:
        candidate_files = []

    if not candidate_files:
        entry_files = search_code(
            repo_path, r"@app\.route|@router\.|def handle|async def post|async def get",
            extensions=[".py", ".ts", ".js"]
        )
        candidate_files = list({r["file"] for r in entry_files})

    if not candidate_files:
        dossier_manager.write_section(
            "data_flow",
            DataFlowAnalysis(agent_name=AGENT_NAME),
        )
        dossier_manager.mark_agent_complete(AGENT_NAME)
        return

    # Prepend call_graph_summary as context if available
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    if compressed is not None and compressed.call_graph_summary:
        messages.append({
            "role": "user",
            "content": f"Call graph summary for context:\n\n{compressed.call_graph_summary[:2000]}",
        })
        messages.append({"role": "assistant", "content": "Understood. I'll use this to trace data flows."})

    for file_rel in candidate_files[:10]:  # cap at 10 entry points
        if steps >= MAX_STEPS or (time.time() - start_time) > TIME_LIMIT:
            break

        file_path = f"{repo_path}/{file_rel}"
        if file_path in visited:
            continue
        visited.add(file_path)
        steps += 1

        content = read_file(file_path)
        messages.append({
            "role": "user",
            "content": f"Trace data flows in:\n\nFile: {file_rel}\n\n```\n{content[:2000]}\n```"
        })

        try:
            response = chat(messages=messages)
        except Exception as exc:
            logger.warning("DataFlowTracer LLM call failed: %s", exc)
            continue

        messages.append({"role": "assistant", "content": response})
        raw_flows.extend(_extract_flows(response))

        if "STOP" in response:
            break

    # Map raw dicts to DataFlowEdge objects
    edges: list[DataFlowEdge] = []
    for f in raw_flows:
        edges.append(DataFlowEdge(
            source=f.get("entry", ""),
            destination=f.get("destination", ""),
            data_type=f.get("transform", ""),
        ))

    dossier_manager.write_section(
        "data_flow",
        DataFlowAnalysis(
            agent_name=AGENT_NAME,
            flows=edges,
        ),
    )
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("DataFlowTracer: %d flows found in %d steps", len(raw_flows), steps)


def _extract_flows(response: str) -> list[dict]:
    import re
    flows = []
    pattern = re.compile(r"FLOW:\s*entry=(\S+)\s+transform=(.+?)\s+destination=(\S+)")
    for match in pattern.finditer(response):
        flows.append({
            "entry": match.group(1),
            "transform": match.group(2).strip(),
            "destination": match.group(3),
        })
    return flows
