"""V4 Diagrammer Agent — mermaid diagram specialist.

Takes diagram placeholder specs from the Writer and produces validated
mermaid source code using graph/dossier tools for real entity relationships.
Includes self-validation with one LLM retry on failure.
"""

import json
import logging
import time
from typing import Any

from src.wiki.agents.diagram_validator import validate_mermaid
from src.wiki.agents.model import get_wiki_model
from src.wiki.v3_tools.dossier_tools import make_dossier_tools
from src.wiki.v3_tools.graph_tools import make_graph_tools

logger = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────

DIAGRAMMER_SYSTEM = """\
You are a Mermaid diagram specialist. Your job is to produce syntactically \
correct, informative Mermaid diagrams for a technical wiki.

You have tools to query real code relationships:

**Dossier (AI analysis findings):**
- list_tags(): Available analysis tags
- get_findings(tag): Agent findings for a tag
- get_finding_detail(tag, agent_name): Full agent output
- get_repo_summary(): High-level project overview

**Code graph:**
- get_callers(entity_name): What calls this function/class
- get_callees(entity_name): What this function/class calls
- get_imports(entity_name): Module imports
- get_inheritance(entity_name): Parent/child classes
- get_entity_neighborhood(entity_name): All relationships

## Mermaid v11 Syntax Rules (CRITICAL)

1. Always start with a valid diagram type: `flowchart TD`, `flowchart LR`, \
`sequenceDiagram`, `classDiagram`, `stateDiagram-v2`, `erDiagram`, `gantt`, \
`pie`, `mindmap`, `timeline`, `gitgraph`

2. **ALWAYS quote node labels that contain special characters** \
(parentheses, brackets, dashes, colons, dots, commas):
   - ✅ `A["FastAPI App (main.py)"]`
   - ❌ `A[FastAPI App (main.py)]` — parentheses break parsing

3. For simple labels without special chars, quotes are optional:
   - ✅ `A[Simple Label]`

4. Use double quotes, not single quotes, inside brackets.

5. Keep diagrams focused: **max 12 nodes**. Simplify aggressively if needed.

6. No raw HTML tags in labels (no `<br>`, `<b>`, etc.).

7. Every `subgraph` must have a matching `end`.

8. Arrow syntax: `-->`, `==>`, `-.->`, `--text-->`. No dangling arrows.

9. Use real entity names from your tool results, not invented ones.
10. For the first/top architecture diagram in a section: show only major building \
blocks and top-level flows (no low-level classes/functions).
11. If more detail is needed, split into multiple diagrams by concern \
(e.g., request path, orchestration, data stores) instead of one dense diagram.
12. Prioritize readability over completeness in a single image.

## Your task

You will receive one or more diagram specifications. For each:
1. Read the `type` and `context` fields
2. Use tools to gather real relationships (callers, callees, imports)
3. Generate valid Mermaid source code
4. Output as JSON: a list of diagram results

Output ONLY a JSON array:
```json
[
  {{
    "tag_index": 0,
    "mermaid_source": "flowchart TD\\n    A[\\"Label\\"] --> B[\\"Other\\"]",
    "caption": "Description",
    "valid": true
  }}
]
```
"""

DIAGRAMMER_FIX_PROMPT = """\
The Mermaid diagram you generated has a syntax error:

**Error**: {error}

**Original diagram**:
```
{source}
```

Fix the diagram. Return ONLY the corrected Mermaid source code — no markdown \
fences, no explanation, no JSON wrapper. Just the raw mermaid text.
"""


def _generate_diagrams_batch(
    diagram_specs: list[dict],
    dossier_dict: dict,
    compressed_dict: dict,
) -> list[dict]:
    """Generate mermaid for all diagram specs using a single ReAct session.

    Returns list of {tag_index, mermaid_source, caption, valid} dicts.
    """
    if not diagram_specs:
        return []

    all_tools = make_dossier_tools(dossier_dict, compressed_dict) + make_graph_tools()
    model = get_wiki_model(temperature=0.2)
    model_with_tools = model.bind_tools(all_tools)
    tool_map = {t.name: t for t in all_tools}

    # Build user message with all diagram specs
    specs_text = json.dumps(diagram_specs, indent=2)
    user_msg = (
        f"Generate Mermaid diagrams for these specifications:\n\n{specs_text}\n\n"
        "Use tools to look up real code relationships before generating diagrams. "
        "Then output the JSON array of results."
    )

    messages = [
        {"role": "system", "content": DIAGRAMMER_SYSTEM},
        {"role": "user", "content": user_msg},
    ]

    # ReAct loop
    tool_calls_made = 0
    final_text = ""

    for step in range(12):
        try:
            response = model_with_tools.invoke(messages)
        except Exception as exc:
            logger.warning("Diagrammer step %d failed: %s", step, exc)
            break

        messages.append(response)
        tool_calls = getattr(response, "tool_calls", None) or []

        if not tool_calls:
            final_text = response.content if hasattr(response, "content") else str(response)
            break

        for tc in tool_calls:
            tool_calls_made += 1
            tool_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
            tool_args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
            tool_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", f"call_{tool_calls_made}")

            fn = tool_map.get(tool_name)
            result = fn.invoke(tool_args) if fn else f"Unknown tool: {tool_name}"
            result_str = str(result)
            if len(result_str) > 8000:
                result_str = result_str[:8000] + "\n... [truncated]"

            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": result_str,
            })
    else:
        for msg in reversed(messages):
            if hasattr(msg, "content") and msg.content:
                final_text = msg.content
                break

    # Parse JSON result
    return _parse_diagram_results(final_text, diagram_specs)


def _parse_diagram_results(
    raw_text: str,
    diagram_specs: list[dict],
) -> list[dict]:
    """Parse the diagrammer's JSON output, falling back gracefully."""
    # Try to extract JSON from the response
    text = raw_text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        results = json.loads(text)
        if isinstance(results, list):
            return results
    except json.JSONDecodeError:
        pass

    # Fallback: try to find JSON array in the text
    import re
    m = re.search(r'\[.*\]', text, re.DOTALL)
    if m:
        try:
            results = json.loads(m.group(0))
            if isinstance(results, list):
                return results
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse diagrammer output, returning empty results")
    return [
        {
            "tag_index": spec["tag_index"],
            "mermaid_source": "",
            "caption": spec.get("caption", ""),
            "valid": False,
        }
        for spec in diagram_specs
    ]


def _validate_and_fix(result: dict, model: Any) -> dict:
    """Validate a diagram result and attempt LLM fix if invalid."""
    source = result.get("mermaid_source", "").strip()
    if not source:
        return {**result, "valid": False}

    is_valid, error = validate_mermaid(source)
    if is_valid:
        return {**result, "valid": True}

    logger.info(
        "Diagram tag_index=%d failed validation: %s — attempting fix",
        result.get("tag_index", -1), error,
    )

    # One LLM retry with specific error feedback
    fix_prompt = DIAGRAMMER_FIX_PROMPT.format(error=error, source=source)
    try:
        fix_response = model.invoke([{"role": "user", "content": fix_prompt}])
        fixed_source = fix_response.content.strip() if hasattr(fix_response, "content") else ""
    except Exception as exc:
        logger.warning("Diagram fix LLM call failed: %s", exc)
        return {**result, "valid": False}

    # Strip markdown fences from fix
    if fixed_source.startswith("```"):
        lines = fixed_source.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        fixed_source = "\n".join(lines).strip()

    is_valid_2, error_2 = validate_mermaid(fixed_source)
    if is_valid_2:
        logger.info("Diagram tag_index=%d fixed successfully", result.get("tag_index", -1))
        return {**result, "mermaid_source": fixed_source, "valid": True}

    logger.warning(
        "Diagram tag_index=%d still invalid after fix: %s",
        result.get("tag_index", -1), error_2,
    )
    return {**result, "valid": False}


def v4_diagrammer_node(state: dict) -> dict:
    """LangGraph node: generate validated mermaid for all diagram placeholders."""
    diagram_specs = state.get("diagram_specs") or []
    if not diagram_specs:
        return {"diagram_results": []}

    dossier_dict = state.get("dossier") or {}
    compressed_dict = state.get("compressed") or {}

    t0 = time.monotonic()

    # Generate all diagrams in one batch
    raw_results = _generate_diagrams_batch(diagram_specs, dossier_dict, compressed_dict)

    # Validate and fix each result
    model = get_wiki_model(temperature=0.1)
    validated_results = [_validate_and_fix(r, model) for r in raw_results]

    elapsed = time.monotonic() - t0
    valid_count = sum(1 for r in validated_results if r.get("valid"))
    logger.info(
        "Diagrammer: %d/%d diagrams valid, %.1fs",
        valid_count, len(validated_results), elapsed,
    )

    return {"diagram_results": validated_results}
