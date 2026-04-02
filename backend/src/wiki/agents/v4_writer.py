"""V4 Writer Agent — prose-focused section writer with XML placeholders.

Writes structured technical prose using dossier/graph tools for research.
Emits self-closing <diagram/> and <code/> XML tags as placeholders for
downstream specialist agents (Diagrammer, Code Embedder).

Does NOT generate mermaid syntax or raw code — only placement + context.
"""

import logging
import re
import time
from typing import Any, Optional

from src.wiki.agents.model import get_wiki_model
from src.wiki.agents.v4_placeholder_parser import parse_placeholders
from src.wiki.v3_tools.dossier_tools import make_dossier_tools
from src.wiki.v3_tools.file_tools import make_file_tools
from src.wiki.v3_tools.graph_tools import make_graph_tools

logger = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────

WRITER_SYSTEM = """\
You are a senior technical writer creating a detailed wiki section for a software project.

You have tools to query pre-analyzed project data:

**Dossier (AI analysis findings):**
- list_tags(): See all available analysis tags and counts
- get_findings(tag): Get agent findings for a tag (architecture, security, api-surface, etc.)
- get_finding_detail(tag, agent_name): Drill into a specific agent's full analysis
- get_repo_summary(): Get the high-level project summary and call/import graphs
- get_file_summary(file_path): Get a file's summary, entities, exports (pass "?list" for all files)
- get_directory_summary(dir_path): Get a directory's summary and contents (pass "?list" for all)
- get_key_entities(): Get the top-50 most important code entities

**Code graph (call/import/inheritance relationships):**
- get_graph_stats(): Node and edge counts — check what's available first
- get_callers(entity_name): Who calls this function/class?
- get_callees(entity_name): What does this function/class call?
- get_imports(entity_name): What does this module import?
- get_inheritance(entity_name): Parent and child classes
- get_entity_neighborhood(entity_name): All relationships around an entity

**File system (read actual source code):**
- read_file(path, start_line?, end_line?): Read source code from a file
- search_code(pattern, glob_pattern?): Search for text/regex across files
- list_directory(path?): List files and directories

## Section brief
{section_brief}

## Your output format

Write in clear, engaging technical prose using markdown (## and ### headings).

**For diagrams**, insert a self-closing XML tag at the exact location where the \
diagram should appear. Do NOT write mermaid syntax — a specialist will create it:
```
<diagram type="flowchart" caption="Description shown below diagram" \
context="Detailed instructions: what entities to show, what relationships to \
highlight, the flow direction. Use real entity names from your tool results."/>
```

**For code examples**, insert a self-closing XML tag where the code should appear. \
Do NOT write code yourself — a specialist will retrieve the real source:
```
<code file="path/to/file.py" symbol="function_name" \
context="What this code demonstrates"/>
```
or with explicit line range:
```
<code file="path/to/file.py" lines="10-35" lang="python" \
context="What this code demonstrates"/>
```

**For callouts** (tips, warnings, notes), write them inline:
```
<callout type="warning|info|tip">Your message here</callout>
```

**For cross-references** to other wiki sections:
```
<cross-ref section="Exact Section Title">descriptive link text</cross-ref>
```

## Rules

1. Use get_findings() and get_finding_detail() to gather analysis data — do NOT guess.
2. Use graph tools to discover call chains and relationships.
3. **CRITICAL — Diagram and code placement**: Every <diagram/> and <code/> tag MUST \
appear inline, immediately after the paragraph that introduces or explains it. \
NEVER group diagrams together. NEVER place all diagrams at the end. \
The pattern is: explanatory prose paragraph → <diagram/> or <code/> → next topic. \
If your section has 3 subsections, each subsection should have its own diagram/code \
placed right after the relevant explanation in that subsection.
4. **Top-of-section architecture diagram**: Place one high-level architecture or \
system-context <diagram/> near the top of the section (immediately after the first \
introductory paragraph under the first ## heading), before deep-dive subsections. \
This diagram should summarize the main components and their relationships.
5. **Progressive disclosure for diagrams**: Keep the top diagram simple (about 5-8 \
major nodes, major flows only). If details are needed, add additional focused \
<diagram/> tags below, each covering one subsystem or flow.
6. **Do not cram details**: Avoid listing every class/function in a single diagram. \
Prefer multiple readable diagrams over one dense graph.
7. In <diagram/> context, include real entity/function names from your research.
8. In <code/> tags, provide file path AND symbol name when possible.
9. Do NOT cover topics listed in boundary_hint as out-of-scope.
10. Aim for 800-1500 words of substantive prose per section.
11. Start by calling list_tags() and get_repo_summary() to orient yourself, \
then use read_file() and search_code() to examine actual source code.
12. Your output must be ONLY the wiki section content. Do NOT include \
reasoning, planning, or notes like "I will now..." or "The files do not...". \
Start directly with a ## heading.
"""


def _format_section_brief(spec_dict: dict, other_titles: list[str]) -> str:
    """Format section_spec into a readable brief for the system prompt."""
    title = spec_dict.get("title", "Untitled")
    one_liner = spec_dict.get("one_liner", "")
    sec_type = spec_dict.get("type", "concept")
    focus_tags = spec_dict.get("focus_tags", [])
    seed_files = spec_dict.get("seed_files", [])
    boundary = spec_dict.get("boundary_hint", "")
    cross_refs = spec_dict.get("cross_refs", [])

    lines = [
        f"**Title**: {title}",
        f"**Type**: {sec_type}",
        f"**One-liner**: {one_liner}" if one_liner else "",
        f"**Focus tags**: {', '.join(focus_tags)}" if focus_tags else "",
        f"**Seed files**: {', '.join(seed_files)}" if seed_files else "",
        f"**Boundary**: {boundary}" if boundary else "",
        f"**Cross-refs**: {', '.join(cross_refs)}" if cross_refs else "",
    ]
    if other_titles:
        lines.append(f"**Other sections in this wiki**: {', '.join(other_titles)}")
    return "\n".join(l for l in lines if l)


def _run_react_loop(
    system_prompt: str,
    model_with_tools: Any,
    tools: list,
    seed_files: list[str],
    max_steps: int = 15,
) -> tuple[str, int]:
    """Run a ReAct tool-use loop until the model stops calling tools.

    Returns: (final_markdown_output, tool_calls_made)
    """
    tool_map = {t.name: t for t in tools}
    messages = [{"role": "system", "content": system_prompt}]

    if seed_files:
        files_hint = "Start by using read_file() on these key files: " + ", ".join(seed_files[:5])
    else:
        files_hint = "Start by calling list_tags() and get_repo_summary() to discover what to explore."

    messages.append({
        "role": "user",
        "content": (
            f"{files_hint}\n\n"
            "After exploring, write the complete wiki section using the output "
            "format described. Place diagrams and code examples inline where "
            "they best support the prose. When done, stop calling tools and "
            "output the final section text."
        ),
    })

    tool_calls_made = 0
    final_text = ""

    for step in range(max_steps):
        try:
            response = model_with_tools.invoke(messages)
        except Exception as exc:
            logger.warning("Writer step %d failed: %s", step, exc)
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
            if fn is None:
                tool_result = f"Unknown tool: {tool_name}"
            else:
                try:
                    tool_result = fn.invoke(tool_args)
                except Exception as exc:
                    tool_result = f"Tool error: {exc}"

            result_str = str(tool_result)
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

    return final_text or "", tool_calls_made


def _strip_reasoning_preamble(text: str) -> str:
    """Remove LLM reasoning preamble before the first markdown heading.

    ReAct loops often emit chain-of-thought like "The requested files do not
    exist... I will now write..." before the actual content. Strip it.
    """
    if not text:
        return text

    # Find first markdown heading (# or ##)
    m = re.search(r'^#{1,3}\s+\S', text, re.MULTILINE)
    if m and m.start() > 0:
        stripped = text[:m.start()].strip()
        if stripped:
            logger.info(
                "Stripped %d chars of reasoning preamble before first heading",
                len(stripped),
            )
        return text[m.start():]

    return text


def v4_writer_node(state: dict) -> dict:
    """LangGraph node: Writer agent produces prose with XML placeholders.

    Reads dossier/compressed from state, researches via tools,
    outputs markdown with <diagram/> and <code/> self-closing tags.
    """
    section_spec = state.get("section_spec") or {}
    dossier_dict = state.get("dossier") or {}
    compressed_dict = state.get("compressed") or {}
    wiki_nav_dict = state.get("wiki_nav") or {}
    repo_path = state.get("repo_path") or ""

    other_titles = [
        s.get("title", "")
        for s in wiki_nav_dict.get("sections", [])
        if s.get("slug") != section_spec.get("slug")
    ]

    section_brief = _format_section_brief(section_spec, other_titles)
    system_prompt = WRITER_SYSTEM.format(section_brief=section_brief)

    # Build tool set — dossier + graph + file tools
    all_tools = make_dossier_tools(dossier_dict, compressed_dict) + make_graph_tools()
    if repo_path:
        all_tools += make_file_tools(repo_path)

    model = get_wiki_model(temperature=0.4, max_tokens=8192)
    model_with_tools = model.bind_tools(all_tools)

    t0 = time.monotonic()
    raw_markdown, tool_calls = _run_react_loop(
        system_prompt=system_prompt,
        model_with_tools=model_with_tools,
        tools=all_tools,
        seed_files=section_spec.get("seed_files", []),
    )
    elapsed = time.monotonic() - t0

    # Strip reasoning preamble — everything before the first markdown heading
    raw_markdown = _strip_reasoning_preamble(raw_markdown)

    logger.info(
        "Writer for %r: %d chars, %d tool calls, %.1fs",
        section_spec.get("slug"), len(raw_markdown), tool_calls, elapsed,
    )

    # Parse placeholders from writer output
    diagram_specs, code_specs = parse_placeholders(raw_markdown)

    return {
        "writer_markdown": raw_markdown,
        "diagram_specs": diagram_specs,
        "code_specs": code_specs,
    }
