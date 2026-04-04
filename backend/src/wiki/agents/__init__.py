"""Wiki pipeline agents.

Active runtime pipeline:
  content_planner → v4 section subgraph (writer + diagrammer + code embedder + assembler)
                  → cross_link_resolver → reference_builder

Entry point: src.wiki.wiki_pipeline.generate_wiki_v3().
"""

from src.wiki.agents.graph import configure_progress_reporting, report_agent_progress

__all__ = ["configure_progress_reporting", "report_agent_progress"]
