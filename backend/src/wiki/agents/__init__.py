"""Multi-agent wiki generation pipeline.

Public API:
    run_wiki_pipeline(initial_state, progress_callback) -> final_state
"""

from src.wiki.agents.graph import run_wiki_pipeline
from src.wiki.agents.state import ArchitectureModel, WikiState

__all__ = ["run_wiki_pipeline", "WikiState", "ArchitectureModel"]
