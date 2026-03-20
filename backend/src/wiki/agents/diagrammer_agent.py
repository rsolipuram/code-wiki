"""DIAGRAMMER agent — generates curated Mermaid diagrams.

Produces LLM-curated diagrams with human-readable labels (5-8 nodes max),
replacing the algorithmic 30-node dumps from diagram_generator.py.
Also generates a single repo-level overview diagram.
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.llm.client import chat
from src.wiki.agents.graph import report_agent_progress
from src.wiki.agents.state import ArchitectureModel, WikiState

logger = logging.getLogger(__name__)

DIAGRAMMER_SYSTEM_PROMPT = """You are a diagram specialist creating Mermaid diagrams for technical documentation.

Generate clean, readable Mermaid diagrams that help developers understand code architecture.

RULES:
1. Use 5-12 nodes per diagram for good detail
2. Use human-readable labels like "Triage Agent" not "agents_triage_run_triage"
3. Supported diagram types: graph TD, graph LR, sequenceDiagram, flowchart TD
4. Use simple, clean syntax without complex styling
5. Each diagram must have a caption explaining what it shows
6. Include at least 2 diagrams per section.

SEQUENCE DIAGRAMS (HIGH PRIORITY):
- If the section involves agents handing off to each other, or a frontend calling a backend, you MUST include a `sequenceDiagram`.
- Example for Agent Handoff: `User -> TriageAgent: "Book flight" \n TriageAgent -> FlightAgent: transfer()`
- Example for API: `Client -> Server: POST /chat \n Server -> DB: save()`

ARCHITECTURE DIAGRAMS:
- Use graph TD/LR showing how components depend on each other.

Output JSON array:
[
  {
    "mermaid_source": "sequenceDiagram\\n    participant A as ...\\n    participant B as ...\\n    A->>B: message",
    "caption": "Interaction flow between agents"
  }
]"""


def diagrammer_node(state: WikiState) -> dict:
    """DIAGRAMMER node — generate diagrams for all sections + overview."""
    t0 = time.monotonic()
    logger.info("DIAGRAMMER agent starting")
    report_agent_progress("diagrammer", "running", "Generating diagrams")

    plan = state.get("plan", {})
    architecture = state.get("architecture", {})
    entity_index = state.get("entity_index", {})
    call_graph = state.get("call_graph", {})
    import_graph = state.get("import_graph", {})
    narrated_sections = state.get("narrated_sections", {})

    arch = ArchitectureModel.from_dict(architecture)
    sections = plan.get("sections", [])

    # 1. Generate per-section diagrams in parallel
    section_diagrams = {}

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {}
        for section in sections:
            section_id = section.get("id", "")
            future = pool.submit(
                _generate_section_diagrams,
                section, arch, entity_index, call_graph, import_graph,
            )
            futures[future] = section_id

        for future in as_completed(futures):
            section_id = futures[future]
            try:
                diagrams = future.result(timeout=120)
                section_diagrams[section_id] = diagrams
            except Exception as exc:
                logger.error("DIAGRAMMER: section '%s' failed: %s", section_id, exc)
                section_diagrams[section_id] = []

    # 2. Generate overview diagram from architecture
    overview_diagram = _generate_overview_diagram(arch, plan)

    elapsed = time.monotonic() - t0
    total_diagrams = sum(len(d) for d in section_diagrams.values())
    logger.info(
        "DIAGRAMMER agent complete: %d section diagrams + overview (%.1fs)",
        total_diagrams, elapsed,
    )
    report_agent_progress("diagrammer", "complete", f"{total_diagrams} diagrams generated")

    return {
        "section_diagrams": section_diagrams,
        "overview_diagram": overview_diagram or {},
        "agent_results": [{
            "agent": "diagrammer",
            "success": True,
            "elapsed": elapsed,
            "total_diagrams": total_diagrams + (1 if overview_diagram else 0),
        }],
    }


def _generate_section_diagrams(
    section: dict,
    arch: ArchitectureModel,
    entity_index: dict,
    call_graph: dict,
    import_graph: dict,
) -> list[dict]:
    """Generate 1-3 diagrams for a section."""
    section_title = section.get("title", "")
    section_files = set()
    for sub in section.get("subsections", []):
        section_files.update(sub.get("relevant_files", []))
    for f in section.get("_all_files", []):
        section_files.add(f)

    if not section_files:
        logger.warning("DIAGRAMMER: no files for section '%s'", section_title)
        return []

    # Gather section entities
    section_entities = []
    for qname, info in entity_index.items():
        if info.get("file_path") in section_files:
            section_entities.append({
                "name": info.get("name", qname.rsplit(".", 1)[-1]),
                "qname": qname,
                "type": info.get("entity_type", ""),
            })

    logger.info("DIAGRAMMER: section '%s' — %d files, %d entities", section_title, len(section_files), len(section_entities))

    # Gather call relationships within section
    section_qnames = {e["qname"] for e in section_entities}
    relationships = []
    for caller, callees in call_graph.items():
        if caller in section_qnames:
            for callee in callees:
                if callee in section_qnames:
                    caller_name = entity_index.get(caller, {}).get("name", caller.rsplit(".", 1)[-1])
                    callee_name = entity_index.get(callee, {}).get("name", callee.rsplit(".", 1)[-1])
                    relationships.append(f"{caller_name} calls {callee_name}")

    # NEW: Gather import relationships between files in this section
    for src_file, targets in import_graph.items():
        if src_file in section_files:
            for target in targets:
                if target in section_files:
                    src_name = src_file.rsplit("/", 1)[-1]
                    target_name = target.rsplit("/", 1)[-1]
                    relationships.append(f"{src_name} imports {target_name}")

    if not section_entities and not relationships:
        logger.warning("DIAGRAMMER: no entities or relationships for section '%s'", section_title)
        return []

    # Find component context
    component_context = ""
    for comp in arch.components:
        comp_name = comp.get("name", "")
        if (comp_name.lower() in section_title.lower()
                or section_title.lower() in comp_name.lower()):
            deps = comp.get("dependencies", [])
            if deps:
                component_context = f"Dependencies: {', '.join(deps)}"
            break

    diagram_type = section.get("diagram_type", "architecture")

    prompt = f"""Generate 2-5 Mermaid diagrams for the "{section_title}" section. Include diverse diagram types (architecture, sequence, flowchart).

Key entities ({len(section_entities)}):
{chr(10).join(f'  - {e["name"]} ({e["type"]})' for e in section_entities[:20])}

Call relationships:
{chr(10).join(f'  - {r}' for r in relationships[:15]) or '  (none detected)'}

{f'Component context: {component_context}' if component_context else ''}

Preferred diagram type: {diagram_type}

Generate diagrams showing the most important relationships.
Use 5-12 nodes with human-readable labels.
Include at least one architecture diagram AND one sequence or flowchart diagram.
Output ONLY a JSON array of diagram objects."""

    try:
        response = chat(
            [
                {"role": "system", "content": DIAGRAMMER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4096,
            temperature=0.3,
            cache_ttl=3600,
        ).strip()

        diagrams = _parse_diagrams_response(response)
        logger.info("DIAGRAMMER: parsed %d diagrams for '%s' from response (%d chars)", len(diagrams), section_title, len(response))

        if not diagrams:
            logger.warning("DIAGRAMMER: parse returned 0 diagrams for '%s'. Response preview: %.500s", section_title, response)

        # Validate mermaid syntax
        validated = []
        for d in diagrams[:5]:
            mermaid = d.get("mermaid_source", "")
            if _validate_mermaid(mermaid):
                validated.append(d)
            else:
                logger.warning("DIAGRAMMER: invalid mermaid for '%s'. First line: '%s'", section_title, mermaid.split('\n')[0] if mermaid else '(empty)')

        logger.info("DIAGRAMMER: %d validated diagrams for '%s'", len(validated), section_title)
        return validated

    except Exception as exc:
        logger.error("DIAGRAMMER: LLM call failed for '%s': %s", section_title, exc, exc_info=True)
        return []


def _generate_overview_diagram(
    arch: ArchitectureModel,
    plan: dict,
) -> dict | None:
    """Generate repo-level overview diagram from architecture model."""
    if not arch.diagram_spec:
        # Build from components
        if not arch.components:
            return None

        nodes = []
        edges = []

        for comp in arch.components:
            node_id = re.sub(r"[^a-zA-Z0-9_]", "_", comp["name"].lower())
            nodes.append({"id": node_id, "label": comp["name"]})

            for dep in comp.get("dependencies", []):
                dep_id = re.sub(r"[^a-zA-Z0-9_]", "_", dep.lower())
                edges.append({"from": node_id, "to": dep_id})

        spec = {"overview": {"nodes": nodes, "edges": edges}}
    else:
        spec = arch.diagram_spec

    overview = spec.get("overview", {})
    nodes = overview.get("nodes", [])
    edges = overview.get("edges", [])

    if len(nodes) < 2:
        return None

    # Build mermaid from spec
    lines = ["graph LR"]
    for node in nodes:
        nid = re.sub(r"[^a-zA-Z0-9_]", "_", node.get("id", ""))
        label = node.get("label", nid)
        lines.append(f"    {nid}[{label}]")

    for edge in edges:
        from_id = re.sub(r"[^a-zA-Z0-9_]", "_", edge.get("from", ""))
        to_id = re.sub(r"[^a-zA-Z0-9_]", "_", edge.get("to", ""))
        label = edge.get("label", "")
        if label:
            lines.append(f"    {from_id} -->|{label}| {to_id}")
        else:
            lines.append(f"    {from_id} --> {to_id}")

    mermaid_source = "\n".join(lines)
    caption = f"Repository Overview — {len(nodes)} components"

    return {"mermaid_source": mermaid_source, "caption": caption}


def _parse_diagrams_response(response: str) -> list[dict]:
    """Parse LLM response into list of diagram dicts."""
    text = response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "mermaid_source" in data:
            return [data]
        return []
    except json.JSONDecodeError:
        # Try to find JSON array in response
        match = re.search(r"\[[\s\S]*\]", text)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass

        # Try to extract mermaid directly
        mermaid_match = re.search(r"(graph\s+(?:TD|LR|TB|BT|RL)[\s\S]*?)(?:\n\n|$)", text)
        if mermaid_match:
            return [{"mermaid_source": mermaid_match.group(1).strip(), "caption": "Component diagram"}]

        return []


def _validate_mermaid(source: str) -> bool:
    """Validation that Mermaid source is minimally well-formed."""
    if not source or len(source) < 10:
        return False
    lines = [ln.rstrip() for ln in source.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return False

    first_line = lines[0].strip()
    valid_starts = ("graph ", "sequenceDiagram", "classDiagram", "flowchart ")
    if not any(first_line.startswith(s) for s in valid_starts):
        return False

    if first_line.startswith("graph ") or first_line.startswith("flowchart "):
        has_edge = any("-->" in ln or "---" in ln for ln in lines[1:])
        if not has_edge:
            return False

    if first_line.startswith("sequenceDiagram"):
        has_participant_or_message = any(
            ln.lstrip().startswith("participant ") or "->" in ln
            for ln in lines[1:]
        )
        if not has_participant_or_message:
            return False

    if first_line.startswith("classDiagram"):
        has_class_or_relation = any(
            ln.lstrip().startswith("class ") or "--" in ln
            for ln in lines[1:]
        )
        if not has_class_or_relation:
            return False

    lowered = source.lower()
    if "would be here" in lowered or "representative line range" in lowered:
        return False

    return True
