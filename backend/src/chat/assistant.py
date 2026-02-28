"""Chat assistant — generates LLM responses with RAG context (T093).

Takes a user question + retrieved context, calls the LLM, and returns a
structured response with code references for the API.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.llm.client import chat as llm_chat

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an expert code documentation assistant.
You answer developer questions about a specific codebase using retrieved code context.

Rules:
- Answer based ONLY on the provided context. Never hallucinate code or behavior.
- Include specific references to functions, classes, or files when relevant.
- Format code snippets in markdown code blocks with the language specified.
- Keep answers concise but complete (200-400 words typical).
- If the context doesn't contain enough information, say so clearly.
"""

_ANSWER_PROMPT = """Developer question: {question}

Retrieved context from the codebase:
{context_text}

Conversation history:
{history}

Answer the question based on the context above. Include:
1. A direct answer to the question
2. Relevant code references (function names, file paths)
3. Any important caveats or gotchas from the context

Format: Plain text with markdown code blocks where helpful."""


def generate_response(
    question: str,
    context: dict[str, Any],
    conversation_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Generate a chat response using LLM with retrieved context.

    Args:
        question: The user's question.
        context: Dict from context_builder.build_context().
        conversation_history: Prior messages [{role, content}] for multi-turn.

    Returns:
        Dict with: content (str), references (list), timestamp (datetime).
    """
    history_str = _format_history(conversation_history or [])

    prompt = _ANSWER_PROMPT.format(
        question=question,
        context_text=context.get("context_text", "No context available."),
        history=history_str or "(No prior conversation)",
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    try:
        response_text = llm_chat(
            messages=messages,
            temperature=0.3,
            max_tokens=1024,
            cache_ttl=300,  # 5-minute cache for chat responses
        )
    except Exception as exc:
        logger.error("Chat LLM call failed: %s", exc)
        response_text = (
            "I'm unable to answer right now — the AI model is unavailable. "
            "Please check that LM Studio is running on localhost:1234."
        )

    return {
        "content": response_text,
        "references": context.get("references", []),
        "timestamp": datetime.now(timezone.utc),
    }


def _format_history(history: list[dict[str, str]]) -> str:
    """Format conversation history for injection into the prompt."""
    if not history:
        return ""
    lines = []
    for msg in history[-6:]:  # last 6 messages (3 turns) for context window
        role = msg.get("role", "user").upper()
        content = msg.get("content", "")[:500]  # truncate long messages
        lines.append(f"{role}: {content}")
    return "\n".join(lines)
