"""Pydantic schemas for chat conversation endpoints."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class ChatMessageReference(BaseModel):
    type: str  # wiki_page | code_entity | file
    id: str
    title: str


class ChatMessageResponse(BaseModel):
    role: str  # user | assistant
    content: str
    timestamp: datetime
    references: list[ChatMessageReference] = []


class ChatConversationResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    repository_id: UUID
    messages: list[ChatMessageResponse] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    content: str
