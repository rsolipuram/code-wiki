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
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """Create LM Studio-backed chat model for wiki agents.

    When max_tokens is None the model uses its full output capacity
    (e.g. 128 K for GPT-5 mini).  Pass an explicit value only for
    intentionally small outputs like critic verdicts or code embeddings.
    """
    settings = get_settings()
    # Local models are slower — use generous timeout
    timeout = 300.0 if settings.llm_provider == "lmstudio" else 120.0
    kwargs: dict = dict(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=temperature,
        timeout=timeout,
    )
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatOpenAI(**kwargs)
