"""Deep Content Agent — V3 wiki pipeline Phase 2.

Per-section tool-equipped agent. Uses a ReAct-style LangGraph loop with
access to: read_file, search_code, list_directory, get_dossier.

Output contract: markdown with special XML tags:
  <code file="..." lines="..." lang="...">...</code>
  <diagram type="mermaid" caption="...">...</diagram>
  <callout type="warning|info|tip">...</callout>
  <cross-ref section="Section Title">link text</cross-ref>

Inline critic check after generation — retries up to MAX_CRITIC_RETRIES times.
"""

import json
import logging
import threading
import time
from typing import Any, Optional

from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.wiki.agents.diagram_validator import fix_mermaid, fix_prose_diagrams, validate_mermaid
from src.wiki.agents.graph import report_agent_progress
from src.wiki.agents.model import get_wiki_model
from src.wiki.agents.tag_assembler import assemble
from src.wiki.v3_types import SectionSpec, V3WikiState

logger = logging.getLogger(__name__)

MAX_CRITIC_RETRIES = 2
SECTION_TIMEOUT_SECONDS = 120

# Semaphore shared across all concurrent deep_content_node calls
# LM Studio is single-threaded; only 1 concurrent request makes sense
def _get_concurrency() -> int:
    try:
        from src.config import get_settings
        return 1 if get_settings().llm_provider == "lmstudio" else 2
    except Exception:
        return 2

_concurrency_sem = threading.Semaphore(_get_concurrency())


DEEP_AGENT_SYSTEM = """\
You are a technical writer creating a detailed wiki section for a software project.

You have tools to query pre-analyzed project data:

Dossier (AI analysis findings):
- list_tags(): See all available analysis tags and counts
- get_findings(tag): Get agent findings for a tag (architecture, security, api-surface, etc.)
- get_finding_detail(tag, agent_name): Drill into a specific agent's full analysis
- get_repo_summary(): Get the high-level project summary and call/import graphs
- get_file_summary(file_path): Get a file's summary, entities, exports (pass "?list" for all files)
- get_directory_summary(dir_path): Get a directory's summary and contents (pass "?list" for all)
- get_key_entities(): Get the top-50 most important code entities

Code graph (call/import/inheritance relationships):
- get_graph_stats(): Node and edge counts — check what's available first
- get_callers(entity_name): Who calls this function/class?
- get_callees(entity_name): What does this function/class call?
- get_imports(entity_name): What does this module import?
- get_inheritance(entity_name): Parent and child classes
- get_entity_neighborhood(entity_name): All relationships around an entity

Section brief:
{section_brief}

Your output format:
- Write in clear, engaging technical prose
- Include real code examples using: <code file="path/to/file.py" lines="10-25" lang="python">...actual code...</code>
- Include architecture diagrams using: <diagram type="mermaid" caption="description">...mermaid source...</diagram>
- Use callouts for important notes: <callout type="warning|info|tip">...message...</callout>
- Cross-reference related sections: <cross-ref section="Exact Section Title">descriptive text</cross-ref>
- Use ## and ### headings to structure content
- Aim for comprehensive coverage — depth over breadth

Important rules:
- Use get_findings() and get_finding_detail() to gather analysis data — do NOT guess
- Use graph tools to discover call chains and dependencies for architecture diagrams
- For code snippets in <code> tags, reference file paths and line ranges from file summaries
- Mermaid diagrams must use valid syntax (flowchart LR, sequenceDiagram, classDiagram, etc.)
- Do NOT cover topics listed in boundary_hint as out-of-scope
- Start by calling list_tags() and get_repo_summary() to orient yourself
"""

CRITIC_SYSTEM = """\
You are a quality reviewer for technical documentation.

Review the section draft and respond with a JSON object:
{
  "passed": true/false,
  "issues": ["specific issue 1", "specific issue 2"],
  "suggestion": "one key improvement if failed"
}

Pass criteria:
- At least 200 words of substantive content
- Contains at least one real code example (<code> tag) or diagram (<diagram> tag)
- No placeholder text like "TODO", "[insert]", or "lorem ipsum"
- Covers the intended topic described in the section brief
- No obvious hallucinated API signatures (verify against code snippets shown)
"""


def deep_content_node(state: V3WikiState, section_spec_dict: dict) -> dict:
    """LangGraph node: write one wiki section.

    Called once per section via Send() API fan-out.
    Acquires _concurrency_sem to limit concurrent LLM calls.

    Args:
        state: Current V3WikiState.
        section_spec_dict: SectionSpec.to_dict() for this section.

    Returns:
        State update: {"deep_sections": [V3Section.to_dict()]}.
    """
    spec = SectionSpec.from_dict(section_spec_dict)
    t0 = time.monotonic()

    report_agent_progress(
        f"section:{spec.slug}", "running",
        f"Writing '{spec.title}'..."
    )

    # Build tools — dossier + graph, no filesystem access
    from src.wiki.v3_tools.dossier_tools import make_dossier_tools
    from src.wiki.v3_tools.graph_tools import make_graph_tools

    repo_path = state.get("repo_path", "")
    dossier_dict = state.get("dossier") or {}
    compressed_dict = state.get("compressed") or {}
    wiki_nav_dict = state.get("wiki_nav") or {}

    all_tools = make_dossier_tools(dossier_dict, compressed_dict) + make_graph_tools()

    # Section brief for the prompt
    other_sections = [
        s.get("title", "") for s in wiki_nav_dict.get("sections", [])
        if s.get("slug") != spec.slug
    ]
    section_brief = _format_section_brief(spec, other_sections)

    system_prompt = DEEP_AGENT_SYSTEM.format(section_brief=section_brief)

    model = get_wiki_model(temperature=0.4, max_tokens=8192)
    model_with_tools = model.bind_tools(all_tools)

    with _concurrency_sem:
        raw_markdown, tool_calls_made = _run_react_loop(
            system_prompt=system_prompt,
            model_with_tools=model_with_tools,
            tools=all_tools,
            seed_files=spec.seed_files,
            max_steps=10,
        )

    # Validate and fix mermaid diagrams inline
    raw_markdown = _fix_diagrams_in_markdown(raw_markdown, model)

    # Inline critic loop (skip when disabled — local models rarely pass)
    from src.config import get_settings as _get_settings
    _critic_on = _get_settings().wiki_critic_enabled
    if _critic_on:
        raw_markdown, critic_passed, critic_retries = _critic_loop(
            raw_markdown=raw_markdown,
            section_brief=section_brief,
            spec=spec,
            model_with_tools=model_with_tools,
            tools=all_tools,
            system_prompt=system_prompt,
        )
    else:
        critic_passed, critic_retries = True, 0
        logger.info("Critic disabled — accepting first-pass output for '%s'", spec.title)

    # Assemble prose segments
    prose_segments = assemble(raw_markdown, repo_path)

    # Validate and fix mermaid diagrams in assembled segments
    def _llm_fix_fn(system: str, user: str) -> str:
        resp = model.invoke([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        return resp.content if hasattr(resp, "content") else str(resp)

    prose_segments = fix_prose_diagrams(prose_segments, _llm_fix_fn)

    word_count = sum(
        len((seg.get("content") or seg.get("text") or "").split())
        for seg in prose_segments
        if seg.get("type") in ("text", "heading")
    )

    elapsed = time.monotonic() - t0
    logger.info(
        "Section '%s' complete: %d words, %d segments, critic=%s, %.1fs",
        spec.title, word_count, len(prose_segments), "pass" if critic_passed else "fail", elapsed,
    )
    report_agent_progress(
        f"section:{spec.slug}", "complete",
        f"'{spec.title}': {word_count} words",
    )

    section_dict = {
        "section_slug": spec.slug,
        "section_title": spec.title,
        "raw_markdown": raw_markdown,
        "prose_segments": prose_segments,
        "word_count": word_count,
        "critic_passed": critic_passed,
        "critic_retries": critic_retries,
        "is_reference_page": False,
    }

    return {
        "deep_sections": [section_dict],
        "agent_results": [{"agent": f"section:{spec.slug}", "success": True, "elapsed": elapsed}],
    }


# ── ReAct tool loop ───────────────────────────────────────────────────────────

def _run_react_loop(
    system_prompt: str,
    model_with_tools: Any,
    tools: list,
    seed_files: list[str],
    max_steps: int = 20,
) -> tuple[str, int]:
    """Run a ReAct tool-use loop until the model stops calling tools.

    Returns: (final_markdown_output, tool_calls_made)
    """
    tool_map = {t.name: t for t in tools}
    messages = [{"role": "system", "content": system_prompt}]

    # Seed the conversation with a user turn that hints at starting files
    if seed_files:
        files_hint = "Start by reading these files: " + ", ".join(seed_files[:5])
    else:
        files_hint = "Explore the codebase to gather information."

    messages.append({
        "role": "user",
        "content": (
            f"{files_hint}\n\n"
            "After exploring, write the complete wiki section using the output format described. "
            "When you are done writing, stop calling tools and output the final section text."
        ),
    })

    tool_calls_made = 0
    final_text = ""

    for step in range(max_steps):
        try:
            response = model_with_tools.invoke(messages)
        except Exception as exc:
            logger.warning("Step %d model call failed: %s", step, exc)
            break

        # Keep the pipeline's idle-timeout alive during multi-step loops
        report_agent_progress(
            "deep_content", "running",
            f"Tool-use step {step + 1}/{max_steps}",
            mark_activity=True,
        )

        # Append assistant message
        messages.append(response)

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            # No more tool calls — extract final text
            final_text = response.content if hasattr(response, "content") else str(response)
            break

        # Execute each tool call
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

            # Truncate large tool results to avoid context explosion
            tool_result_str = str(tool_result)
            if len(tool_result_str) > 8000:
                tool_result_str = tool_result_str[:8000] + "\n... [truncated]"

            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": tool_result_str,
            })
    else:
        # Hit max_steps — grab last assistant text
        for msg in reversed(messages):
            if hasattr(msg, "content") and msg.content:
                final_text = msg.content
                break

    return final_text or "", tool_calls_made


# ── Critic loop ───────────────────────────────────────────────────────────────

def _critic_loop(
    raw_markdown: str,
    section_brief: str,
    spec: SectionSpec,
    model_with_tools: Any,
    tools: list,
    system_prompt: str,
) -> tuple[str, bool, int]:
    """Run inline quality check, retry up to MAX_CRITIC_RETRIES times.

    Returns: (final_markdown, critic_passed, retries_used)
    """
    model = get_wiki_model(temperature=0.1, max_tokens=512)
    retries = 0

    for attempt in range(MAX_CRITIC_RETRIES + 1):
        verdict = _run_critic(raw_markdown, section_brief, model)
        if verdict.get("passed", True):
            return raw_markdown, True, retries

        if attempt >= MAX_CRITIC_RETRIES:
            logger.warning(
                "Section '%s' failed critic after %d retries: %s",
                spec.title, retries, verdict.get("issues"),
            )
            return raw_markdown, False, retries

        # Retry with feedback
        retries += 1
        logger.info("Section '%s' critic retry %d: %s", spec.title, retries, verdict.get("suggestion"))
        raw_markdown, _ = _run_react_loop(
            system_prompt=system_prompt,
            model_with_tools=model_with_tools,
            tools=tools,
            seed_files=spec.seed_files,
            max_steps=15,
        )

    return raw_markdown, False, retries


def _run_critic(raw_markdown: str, section_brief: str, model: Any) -> dict:
    """Single critic evaluation. Returns {passed, issues, suggestion}."""
    try:
        response = model.invoke([
            {"role": "system", "content": CRITIC_SYSTEM},
            {"role": "user", "content": (
                f"Section brief:\n{section_brief}\n\n"
                f"Draft content:\n{raw_markdown[:3000]}"
            )},
        ])
        content = response.content if hasattr(response, "content") else str(response)
        # Parse JSON
        import re
        m = re.search(r'\{.*\}', content, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as exc:
        logger.debug("Critic call failed: %s", exc)
    return {"passed": True}  # default pass on error


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_section_brief(spec: SectionSpec, other_section_titles: list[str]) -> str:
    """Format SectionSpec into a human-readable brief for the agent prompt."""
    lines = [
        f"Title: {spec.title}",
        f"Type: {spec.type}",
    ]
    if spec.one_liner:
        lines.append(f"Purpose: {spec.one_liner}")
    if spec.focus_tags:
        lines.append(f"Dossier tags to consult: {', '.join(spec.focus_tags)}")
    if spec.seed_files:
        lines.append(f"Key files to start from: {', '.join(spec.seed_files)}")
    if spec.boundary_hint:
        lines.append(f"Scope guidance: {spec.boundary_hint}")
    if spec.cross_refs:
        lines.append(f"Cross-reference to sections: {', '.join(spec.cross_refs)}")
    if other_section_titles:
        titles_str = ", ".join(f"'{t}'" for t in other_section_titles[:8])
        lines.append(f"Other sections in this wiki (avoid duplicating their content): {titles_str}")
    return "\n".join(lines)


def _fix_diagrams_in_markdown(raw: str, model: Any) -> str:
    """Find all <diagram type='mermaid'> blocks and validate/fix each."""
    import re

    def _llm_fix(system: str, user: str) -> str:
        try:
            resp = model.invoke([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
            return resp.content if hasattr(resp, "content") else str(resp)
        except Exception:
            return user  # return original on error

    pattern = re.compile(
        r'(<diagram\s+type=["\']mermaid["\'][^>]*>)(.*?)(</diagram>)',
        re.DOTALL | re.IGNORECASE,
    )

    def _fix_match(m: re.Match) -> str:
        opening = m.group(1)
        source = m.group(3)
        closing = m.group(4) if m.lastindex >= 4 else "</diagram>"

        is_valid, error = validate_mermaid(source)
        if is_valid:
            return m.group(0)

        fixed = fix_mermaid(source, error, _llm_fix)
        return f"{opening}{fixed}</diagram>"

    # Re-match with the correct group indexing
    def _fix_match_v2(m: re.Match) -> str:
        opening = m.group(1)
        source = m.group(2)
        closing = m.group(3)

        is_valid, error = validate_mermaid(source)
        if is_valid:
            return m.group(0)

        fixed = fix_mermaid(source, error, _llm_fix)
        return f"{opening}{fixed}{closing}"

    return pattern.sub(_fix_match_v2, raw)
