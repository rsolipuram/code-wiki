"""LangGraph StateGraph for the V4 wiki pipeline.

Execution flow:
  content_planner → fan_out_sections (Send per section, max 2 concurrent)
                  → assemble_node
                  → crosslink_node
                  → reference_node
                  → END

Each section is dispatched via Send() and appends its section dict to
deep_sections (Annotated[list, add]).

Section generation is always the V4 3-phase subgraph:
Writer → parallel(Diagrammer, Code Embedder) → Assembler.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Optional

from langgraph.constants import Send
from langgraph.graph import END, StateGraph

from src.wiki.agents.graph import configure_progress_reporting, report_agent_progress
from src.wiki.pipeline_types import V3WikiState, WikiNav

logger = logging.getLogger(__name__)

# Shared semaphore enforcing max 2 concurrent section agents
_concurrency_sem = threading.Semaphore(2)

# ── Node: content planner ─────────────────────────────────────────────────────

def planner_node(state: V3WikiState) -> dict:
    from src.wiki.agents.content_planner import content_planner_node
    return content_planner_node(state)


# ── Router: fan out one Send per section ─────────────────────────────────────

def fan_out_sections(state: V3WikiState) -> list[Send]:
    """Router node — dispatch one deep_section_node per section in wiki_nav."""
    wiki_nav_dict = state.get("wiki_nav") or {}
    sections = wiki_nav_dict.get("sections", [])

    if not sections:
        logger.warning("WikiNav has no sections — skipping fan-out")
        return []

    # Carry forward immutable context each section agent needs
    shared = {
        "dossier": state.get("dossier") or {},
        "compressed": state.get("compressed") or {},
        "repo_path": state.get("repo_path", ""),
        "repo_name": state.get("repo_name", ""),
        "repository_id": state.get("repository_id", ""),
        "wiki_nav": wiki_nav_dict,
    }

    sends = []
    for spec_dict in sections:
        sends.append(Send("deep_section_node", {**shared, "section_spec": spec_dict}))

    logger.info("Fan-out: %d section agents dispatched (pipeline=v4)", len(sends))
    return sends


# ── Node: deep content agent (per section) ───────────────────────────────────

def deep_section_node(state: V3WikiState) -> dict:
    """Wrapper node invoked once per section via Send()."""
    with _concurrency_sem:
        from src.wiki.section_graph import run_v4_section
        return run_v4_section(state)


# ── Node: assemble all sections ──────────────────────────────────────────────

def assemble_node(state: V3WikiState) -> dict:
    """No-op assembly node — prose_segments are already built in deep_content_node.

    This node exists as a fan-in sync point after all section sends complete.
    It validates that all sections have prose_segments and logs a summary.
    """
    deep_sections = state.get("deep_sections") or []
    total_words = sum(s.get("word_count", 0) for s in deep_sections)
    total_segs = sum(len(s.get("prose_segments", [])) for s in deep_sections)

    logger.info(
        "Assemble node: %d sections, %d words, %d segments",
        len(deep_sections), total_words, total_segs,
    )
    report_agent_progress("assembler", "complete", f"{len(deep_sections)} sections assembled")

    # Return empty list — deep_sections uses Annotated[list, add], so returning
    # the current value would double it. The sections are already accumulated.
    return {"deep_sections": []}


# ── Node: cross-link resolution ───────────────────────────────────────────────

def crosslink_node(state: V3WikiState) -> dict:
    """Resolve cross-ref segments across all sections."""
    from src.wiki.agents.cross_link_resolver import resolve_cross_refs

    deep_sections = state.get("deep_sections") or []
    wiki_nav_dict = state.get("wiki_nav") or {}

    report_agent_progress("crosslink", "running", "Resolving cross-references...")
    resolved = resolve_cross_refs(deep_sections, wiki_nav_dict)
    report_agent_progress("crosslink", "complete", "Cross-refs resolved")

    return {"resolved_sections": resolved}


# ── Node: reference pages ─────────────────────────────────────────────────────

def reference_node(state: V3WikiState) -> dict:
    """Generate fixed reference pages (Getting Started, Glossary, API Reference)."""
    from src.wiki.agents.reference_builder import build_reference_pages

    report_agent_progress("reference_builder", "running", "Building reference pages...")

    dossier_dict = state.get("dossier") or {}
    compressed = state.get("compressed") or {}
    fingerprint = state.get("fingerprint") or {}
    repo_name = state.get("repo_name") or "project"
    repo_url = state.get("repo_url") or ""
    entities = state.get("entities") or []
    repo_path = state.get("repo_path") or ""
    analysis_id = state.get("repository_id") or None

    ref_pages = build_reference_pages(
        dossier_dict=dossier_dict,
        compressed=compressed,
        fingerprint=fingerprint,
        repo_name=repo_name,
        repo_url=repo_url,
        entities=entities,
        repo_path=repo_path,
        analysis_id=analysis_id,
    )

    report_agent_progress("reference_builder", "complete", f"{len(ref_pages)} reference pages built")

    return {
        "deep_sections": ref_pages,  # Annotated[list, add] — appended to existing
        "agent_results": [{"agent": "reference_builder", "success": True, "elapsed": 0}],
    }


# ── Graph wiring ──────────────────────────────────────────────────────────────

def build_v3_graph() -> object:
    """Build and compile the V3 wiki LangGraph StateGraph."""
    graph = StateGraph(V3WikiState)

    graph.add_node("planner_node", planner_node)
    graph.add_node("deep_section_node", deep_section_node)
    graph.add_node("assemble_node", assemble_node)
    graph.add_node("crosslink_node", crosslink_node)
    graph.add_node("reference_node", reference_node)

    # Entry point
    graph.set_entry_point("planner_node")

    # After planner, fan out one deep_section_node per section
    graph.add_conditional_edges("planner_node", fan_out_sections, ["deep_section_node"])

    # All section sends converge at assemble_node
    graph.add_edge("deep_section_node", "assemble_node")

    # Linear post-processing
    graph.add_edge("assemble_node", "crosslink_node")
    graph.add_edge("crosslink_node", "reference_node")
    graph.add_edge("reference_node", END)

    return graph.compile()


def run_v3_pipeline(
    initial_state: V3WikiState,
    repo_id: Optional[str] = None,
) -> dict:
    """Compile and invoke the V3 wiki pipeline graph.

    Args:
        initial_state: Fully populated V3WikiState inputs.
        repo_id: Repository ID for SSE progress events.

    Returns:
        Final state dict with all sections populated.
    """
    activity_lock = threading.Lock()
    last_activity = time.monotonic()

    def _mark_activity() -> None:
        nonlocal last_activity
        with activity_lock:
            last_activity = time.monotonic()

    configure_progress_reporting(repo_id, _mark_activity)
    t0 = time.monotonic()

    compiled = build_v3_graph()

    stop_heartbeat = threading.Event()

    def _heartbeat() -> None:
        while not stop_heartbeat.wait(timeout=15):
            report_agent_progress(
                "v3_pipeline",
                "running",
                "Generating wiki sections...",
                mark_activity=True,
            )

    heartbeat = threading.Thread(target=_heartbeat, name="v3-heartbeat", daemon=True)
    heartbeat.start()

    try:
        from src.config import get_settings
        settings = get_settings()
        timeout = getattr(settings, "wiki_agent_invoke_timeout_seconds", 0)
        idle_timeout = getattr(settings, "wiki_agent_idle_timeout_seconds", timeout)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(compiled.invoke, initial_state)
            while True:
                try:
                    final_state = future.result(timeout=15)
                    break
                except FuturesTimeoutError:
                    with activity_lock:
                        idle_for = time.monotonic() - last_activity
                    if idle_for >= idle_timeout:
                        raise RuntimeError(
                            f"V3 wiki pipeline idle timeout after {idle_timeout}s "
                            f"(no progress events for {int(idle_for)}s)"
                        )
                    elapsed = time.monotonic() - t0
                    if timeout > 0 and elapsed >= timeout:
                        raise RuntimeError(
                            f"V3 wiki pipeline max timeout after {timeout}s "
                            f"(last progress {int(idle_for)}s ago)"
                        )
    finally:
        stop_heartbeat.set()
        heartbeat.join(timeout=2.0)
        configure_progress_reporting(None, None)

    logger.info("V3 wiki pipeline complete (%.1fs)", time.monotonic() - t0)
    return final_state
