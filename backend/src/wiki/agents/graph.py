"""LangGraph StateGraph orchestrator for the wiki agent pipeline.

Execution flow:
  architect → planner → writer → critic → (pass) → [annotator, diagrammer, tabulator] → assembler
                                         ↑                ↓ (fail, retry ≤ 2×)
                                         └── writer (retry)

Each node function creates agents, invokes them with relevant state slices,
and returns state updates.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Callable, Optional

from langgraph.graph import StateGraph, END

from src.wiki.agents.state import WikiState
from src.config import get_settings

logger = logging.getLogger(__name__)

# Module-level repo_id used by agent nodes for progress reporting.
# Set by run_wiki_pipeline() before graph execution.
_current_repo_id: Optional[str] = None


def report_agent_progress(agent_name: str, status: str, detail: str = "") -> None:
    """Publish an agent-level progress event to Redis.

    Called by agent nodes at start and end of execution.

    Args:
        agent_name: e.g. "architect", "planner", "writer"
        status: "running" or "complete"
        detail: optional human-readable detail string
    """
    if not _current_repo_id:
        return
    try:
        from src.api.progress_events import publish_progress
        publish_progress(_current_repo_id, {
            "type": "agent_progress",
            "agent": agent_name,
            "status": status,
            "detail": detail,
            "timestamp": time.time(),
        })
    except Exception:
        logger.debug("Failed to publish agent progress for %s", agent_name, exc_info=True)


def build_wiki_graph() -> StateGraph:
    """Build the wiki generation agent graph.

    Returns a compiled LangGraph StateGraph.
    """
    from src.wiki.agents.architect_agent import architect_node
    from src.wiki.agents.planner_agent import planner_node
    from src.wiki.agents.writer_agent import writer_node
    from src.wiki.agents.annotator_agent import annotator_node
    from src.wiki.agents.diagrammer_agent import diagrammer_node
    from src.wiki.agents.tabulator_agent import tabulator_node
    from src.wiki.agents.assembler_agent import assembler_node

    from src.wiki.agents.architect_agent import architect_node
    from src.wiki.agents.planner_agent import planner_node
    from src.wiki.agents.writer_agent import writer_node
    from src.wiki.agents.critic_agent import critic_node, critic_route, MAX_RETRIES
    from src.wiki.agents.annotator_agent import annotator_node
    from src.wiki.agents.diagrammer_agent import diagrammer_node
    from src.wiki.agents.tabulator_agent import tabulator_node
    from src.wiki.agents.assembler_agent import assembler_node

    graph = StateGraph(WikiState)

    graph.add_node("architect", architect_node)
    graph.add_node("planner", planner_node)
    graph.add_node("writer", writer_node)
    graph.add_node("critic", critic_node)
    graph.add_node("annotator", annotator_node)
    graph.add_node("diagrammer", diagrammer_node)
    graph.add_node("tabulator", tabulator_node)
    graph.add_node("assembler", assembler_node)

    graph.set_entry_point("architect")
    graph.add_edge("architect", "planner")
    graph.add_edge("planner", "writer")
    graph.add_edge("writer", "critic")

    # Critic: fan-out to enrichment pipeline on pass, retry writer on fail.
    # We use conditional_edges where "annotator" means: also kick off diagrammer+tabulator.
    # LangGraph 0.2.x doesn't support direct conditional fan-out to multiple nodes,
    # so we implement it as: critic → annotator (always on pass), critic also sends
    # to diagrammer and tabulator via unconditional edges from a pass state.
    # Simplest correct approach: keep annotator as the serial fan-in gatekeeper and
    # have diagrammer/tabulator start from critic pass via conditional edges too.
    def critic_route_annotator(state: WikiState) -> str:
        return critic_route(state)

    def critic_route_diagrammer(state: WikiState) -> str:
        result = state.get("critic_result") or {}
        passed = result.get("passed", True)
        retry_count = state.get("writer_retry_count") or 0
        if not passed and retry_count <= MAX_RETRIES:
            return "__end__"
        return "diagrammer"

    def critic_route_tabulator(state: WikiState) -> str:
        result = state.get("critic_result") or {}
        passed = result.get("passed", True)
        retry_count = state.get("writer_retry_count") or 0
        if not passed and retry_count <= MAX_RETRIES:
            return "__end__"
        return "tabulator"

    graph.add_conditional_edges(
        "critic",
        critic_route_annotator,
        {"writer": "writer", "annotator": "annotator"},
    )
    graph.add_conditional_edges(
        "critic",
        critic_route_diagrammer,
        {"diagrammer": "diagrammer", "__end__": END},
    )
    graph.add_conditional_edges(
        "critic",
        critic_route_tabulator,
        {"tabulator": "tabulator", "__end__": END},
    )

    # All three enrichment nodes must complete before assembler
    graph.add_edge("annotator", "assembler")
    graph.add_edge("diagrammer", "assembler")
    graph.add_edge("tabulator", "assembler")
    graph.add_edge("assembler", END)

    return graph.compile()


def run_wiki_pipeline(
    initial_state: WikiState,
    progress_callback: Optional[Callable[[str], None]] = None,
    repo_id: Optional[str] = None,
) -> dict:
    """Compile and invoke the wiki agent graph.

    Args:
        initial_state: WikiState with all inputs populated and outputs empty.
        progress_callback: Optional callback for progress reporting.
        repo_id: Repository ID for Redis pub/sub progress events.

    Returns:
        Final state dict with all agent outputs populated.
    """
    global _current_repo_id
    _current_repo_id = repo_id

    t0 = time.monotonic()

    if progress_callback:
        progress_callback("Compiling agent graph")

    compiled = build_wiki_graph()

    if progress_callback:
        progress_callback("Orchestrating agents...")

    logger.info("Wiki agent pipeline starting")

    settings = get_settings()
    invoke_timeout = max(60, settings.wiki_agent_invoke_timeout_seconds)
    heartbeat_interval = max(5, settings.wiki_agent_heartbeat_seconds)

    stop_heartbeat = threading.Event()

    def _heartbeat_loop() -> None:
        # Keep UI alive while long-running graph execution is active.
        while not stop_heartbeat.wait(timeout=heartbeat_interval):
            if progress_callback:
                progress_callback("Orchestrating agents...")
            report_agent_progress("orchestrator", "running", "Orchestrating agents...")

    heartbeat_thread = threading.Thread(target=_heartbeat_loop, name="wiki-agent-heartbeat", daemon=True)
    heartbeat_thread.start()

    try:
        # Guard against indefinite hangs in graph orchestration.
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(compiled.invoke, initial_state)
            final_state = future.result(timeout=invoke_timeout)
    except FuturesTimeoutError as exc:
        logger.error("Wiki agent pipeline timed out after %ds", invoke_timeout)
        raise RuntimeError(f"Wiki agent pipeline timed out after {invoke_timeout}s") from exc
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=2.0)
        _current_repo_id = None

    elapsed = time.monotonic() - t0
    logger.info("Wiki agent pipeline complete (%.1fs)", elapsed)

    return final_state
