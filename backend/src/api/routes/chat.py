"""Chat conversation endpoints (T094, T095)."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.api.schemas.chat import (
    ChatConversationResponse,
    ChatMessageResponse,
    SendMessageRequest,
)
from src.chat.assistant import generate_response
from src.chat.context_builder import build_context
from src.models.events import ChatConversation
from src.models.repository import Repository

router = APIRouter(tags=["chat"])


def _conv_to_response(conv: ChatConversation) -> ChatConversationResponse:
    messages = [
        ChatMessageResponse(
            role=m["role"],
            content=m["content"],
            timestamp=datetime.fromisoformat(m["timestamp"])
            if isinstance(m.get("timestamp"), str)
            else m.get("timestamp", datetime.now(timezone.utc)),
            references=m.get("references", []),
        )
        for m in (conv.messages or [])
    ]
    return ChatConversationResponse(
        id=UUID(conv.id),
        repository_id=UUID(conv.repository_id),
        messages=messages,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.post(
    "/chat/{repository_id}/conversations",
    status_code=status.HTTP_201_CREATED,
    response_model=ChatConversationResponse,
)
async def create_conversation(
    repository_id: UUID,
    db: Session = Depends(get_db),
) -> ChatConversationResponse:
    """Start a new chat conversation for a repository."""
    repo = db.get(Repository, str(repository_id))
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    conv = ChatConversation(
        repository_id=str(repository_id),
        messages=[],
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return _conv_to_response(conv)


@router.get(
    "/chat/{repository_id}/conversations",
    response_model=list[ChatConversationResponse],
)
async def list_conversations(
    repository_id: UUID,
    db: Session = Depends(get_db),
) -> list[ChatConversationResponse]:
    """List conversations for a repository, most recent first."""
    convs = (
        db.query(ChatConversation)
        .filter_by(repository_id=str(repository_id))
        .order_by(ChatConversation.created_at.desc())  # type: ignore[attr-defined]
        .limit(50)
        .all()
    )
    return [_conv_to_response(c) for c in convs]


@router.post(
    "/chat/conversations/{conversation_id}/messages",
    response_model=ChatMessageResponse,
)
async def send_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    db: Session = Depends(get_db),
) -> ChatMessageResponse:
    """Send a message and receive an AI response.

    1. Appends the user message to the conversation.
    2. Retrieves relevant context via RAG.
    3. Calls LLM to generate a response.
    4. Appends the AI response and persists.

    Returns only the AI response message (not the full conversation).
    """
    conv = db.get(ChatConversation, str(conversation_id))
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    messages: list[dict] = list(conv.messages or [])
    now = datetime.now(timezone.utc)

    # Append user message
    user_msg: dict = {
        "role": "user",
        "content": body.content,
        "timestamp": now.isoformat(),
        "references": [],
    }
    messages.append(user_msg)

    # Build RAG context
    context = build_context(
        question=body.content,
        repository_id=conv.repository_id,
    )

    # Generate AI response
    history = [{"role": m["role"], "content": m["content"]} for m in messages[:-1]]
    result = generate_response(
        question=body.content,
        context=context,
        conversation_history=history,
    )

    ai_msg: dict = {
        "role": "assistant",
        "content": result["content"],
        "timestamp": result["timestamp"].isoformat(),
        "references": result["references"],
    }
    messages.append(ai_msg)

    # Persist updated message list
    conv.messages = messages
    db.commit()

    return ChatMessageResponse(
        role="assistant",
        content=result["content"],
        timestamp=result["timestamp"],
        references=result["references"],
    )
