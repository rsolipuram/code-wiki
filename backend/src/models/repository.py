"""Repository SQLAlchemy model."""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, new_uuid


class RepositoryStatus(str, enum.Enum):
    pending = "pending"
    analyzing = "analyzing"
    ready = "ready"
    error = "error"


class Repository(Base, TimestampMixin):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    owner: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    # JSONB list of detected languages e.g. ["Python", "TypeScript"]
    primary_languages: Mapped[Optional[list[str]]] = mapped_column(JSONB)
    status: Mapped[RepositoryStatus] = mapped_column(
        Enum(RepositoryStatus), nullable=False, default=RepositoryStatus.pending
    )
    branch: Mapped[Optional[str]] = mapped_column(String(255))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    progress: Mapped[Optional[dict]] = mapped_column(JSONB)
    last_analyzed_commit: Mapped[Optional[str]] = mapped_column(String(40))
    last_analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    size_files: Mapped[Optional[int]] = mapped_column(Integer)
    size_lines: Mapped[Optional[int]] = mapped_column(Integer)

    # Relationships
    wikis: Mapped[list["Wiki"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Wiki", back_populates="repository", cascade="all, delete-orphan"
    )
    update_events: Mapped[list["UpdateEvent"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "UpdateEvent", back_populates="repository", cascade="all, delete-orphan"
    )
