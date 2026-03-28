"""V3 wiki pipeline agents.

The V3 pipeline replaces the old 7-agent waterfall with:
  content_planner → deep_content (per section, parallel) → tag_assembler
                  → cross_link_resolver → reference_builder

Entry point: src.wiki.v3_pipeline.generate_wiki_v3()
"""

from src.wiki.agents.graph import configure_progress_reporting, report_agent_progress

__all__ = ["configure_progress_reporting", "report_agent_progress"]
