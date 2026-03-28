"""LM Studio model factory for wiki agents.

Wraps ChatOpenAI with local LM Studio configuration for use
with LangGraph deep agents.
"""

import logging

from langchain_openai import ChatOpenAI

from src.config import get_settings

logger = logging.getLogger(__name__)


def get_wiki_model(
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> ChatOpenAI:
    """Create LM Studio-backed chat model for wiki agents."""
    settings = get_settings()
    # Local models are slower — use generous timeout
    timeout = 300.0 if settings.llm_provider == "lmstudio" else 120.0
    return ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
