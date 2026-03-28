"""V4 Section Subgraph — LangGraph mini-pipeline per wiki section.

Replaces the V3 deep_content_node with a 3-phase pipeline:
  Writer → parallel(Diagrammer, Code Embedder) → Assembler

The subgraph runs inside a Send() invocation, receiving shared state
(dossier, compressed, repo_path, wiki_nav) plus a section_spec.
It returns a V3-compatible section dict for fan-in.
"""

import logging
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph

logger = logging.getLogger(__name__)


# ── V4 Section State ──────────────────────────────────────────────────────────

class V4SectionState(TypedDict, total=False):
    """State for the per-section mini-pipeline."""
    # Immutable inputs (from parent graph via Send)
    dossier: dict
    compressed: dict
    repo_path: str
    repo_name: str
    repository_id: str
    section_spec: dict
    wiki_nav: dict

    # Writer output
    writer_markdown: str
    diagram_specs: list
    code_specs: list

    # Specialist outputs
    diagram_results: list
    code_results: list

    # Final assembled output
    prose_segments: list
    word_count: int
    section_slug: str
    section_title: str


# ── Node wrappers ─────────────────────────────────────────────────────────────

def _writer_node(state: V4SectionState) -> dict:
    from src.wiki.agents.v4_writer import v4_writer_node
    return v4_writer_node(state)


def _diagrammer_node(state: V4SectionState) -> dict:
    from src.wiki.agents.v4_diagrammer import v4_diagrammer_node
    return v4_diagrammer_node(state)


def _code_embedder_node(state: V4SectionState) -> dict:
    from src.wiki.agents.v4_code_embedder import v4_code_embedder_node
    return v4_code_embedder_node(state)


def _assembler_node(state: V4SectionState) -> dict:
    from src.wiki.agents.v4_assembler import v4_assembler_node
    return v4_assembler_node(state)


# ── Subgraph builder ──────────────────────────────────────────────────────────

def build_v4_section_graph() -> object:
    """Build and compile the V4 section mini-pipeline.

    Flow:
        writer → parallel(diagrammer, code_embedder) → assembler → END

    LangGraph doesn't have a native "parallel" construct for non-Send nodes,
    so we wire both specialists as successors of writer and both feed into
    assembler. LangGraph executes nodes with all dependencies met concurrently.
    """
    graph = StateGraph(V4SectionState)

    graph.add_node("writer", _writer_node)
    graph.add_node("diagrammer", _diagrammer_node)
    graph.add_node("code_embedder", _code_embedder_node)
    graph.add_node("assembler", _assembler_node)

    graph.set_entry_point("writer")

    # Writer feeds both specialists
    graph.add_edge("writer", "diagrammer")
    graph.add_edge("writer", "code_embedder")

    # Both specialists feed assembler
    graph.add_edge("diagrammer", "assembler")
    graph.add_edge("code_embedder", "assembler")

    graph.add_edge("assembler", END)

    return graph.compile()


# Pre-compiled subgraph (reused across Send invocations)
_v4_section_compiled = None


def get_v4_section_graph():
    """Get or create the compiled V4 section subgraph."""
    global _v4_section_compiled
    if _v4_section_compiled is None:
        _v4_section_compiled = build_v4_section_graph()
    return _v4_section_compiled


def run_v4_section(state: dict) -> dict:
    """Execute the V4 section pipeline and return V3-compatible output.

    This is called from the main graph's deep_section_node (V4 mode).
    It runs the subgraph and formats the output as a V3Section-compatible dict
    for the existing fan-in and persistence logic.

    Args:
        state: Dict with dossier, compressed, repo_path, section_spec, wiki_nav, etc.

    Returns:
        Dict with deep_sections key containing one V3Section-compatible dict.
    """
    section_spec = state.get("section_spec") or {}
    slug = section_spec.get("slug", "unknown")

    logger.info("V4 section pipeline starting for %r", slug)

    subgraph = get_v4_section_graph()
    final_state = subgraph.invoke(state)

    # Package as V3Section-compatible dict
    section_dict = {
        "section_slug": final_state.get("section_slug", slug),
        "section_title": final_state.get("section_title", section_spec.get("title", "")),
        "raw_markdown": final_state.get("writer_markdown", ""),
        "prose_segments": final_state.get("prose_segments", []),
        "word_count": final_state.get("word_count", 0),
        "critic_passed": True,
        "critic_retries": 0,
        "is_reference_page": False,
    }

    logger.info(
        "V4 section pipeline complete for %r: %d segments, %d words",
        slug, len(section_dict["prose_segments"]), section_dict["word_count"],
    )

    return {"deep_sections": [section_dict]}
