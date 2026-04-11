"""LLM model factory for wiki agents across supported providers.

Wraps ChatOpenAI with provider-resolved configuration for use
with LangGraph deep agents.
"""

import logging

from langchain_openai import ChatOpenAI

from src.config import get_settings
from src.llm.providers import resolve_provider

logger = logging.getLogger(__name__)


def get_wiki_model(
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """Create provider-backed chat model for wiki agents.

    When max_tokens is None the model uses its full output capacity
    (e.g. 128 K for GPT-5 mini).  Pass an explicit value only for
    intentionally small outputs like critic verdicts or code embeddings.
    """
    settings = get_settings()
    config = resolve_provider(settings)
    timeout = config.timeout
    kwargs: dict = dict(
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model,
        temperature=temperature,
        timeout=timeout,
    )
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatOpenAI(**kwargs)
