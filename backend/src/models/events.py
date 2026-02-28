"""ChatConversation and UpdateEvent SQLAlchemy models."""

import enum
from typing import Any, Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, new_uuid


class UpdateEventStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    superseded = "superseded"


class ChatConversation(Base, TimestampMixin):
    __tablename__ = "chat_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[Optional[str]] = mapped_column(String(512))
    # JSONB array of {role, content, references, timestamp}
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class UpdateEvent(Base, TimestampMixin):
    __tablename__ = "update_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    commit_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    # JSONB list of file paths that changed
    changed_files: Mapped[Optional[list[str]]] = mapped_column(JSONB)
    # JSONB list of module IDs affected
    affected_module_ids: Mapped[Optional[list[str]]] = mapped_column(JSONB)
    status: Mapped[UpdateEventStatus] = mapped_column(
        String(20), nullable=False, default=UpdateEventStatus.pending
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    repository: Mapped["Repository"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Repository", back_populates="update_events"
    )
