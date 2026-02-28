"""Wiki and WikiPage SQLAlchemy models."""

import enum
from typing import Any, Optional

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, new_uuid


class PageType(str, enum.Enum):
    home = "home"
    module = "module"
    getting_started = "getting_started"
    api_reference = "api_reference"
    glossary = "glossary"
    function_index = "function_index"


class Wiki(Base, TimestampMixin):
    __tablename__ = "wikis"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    module_count: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)

    # Relationships
    repository: Mapped["Repository"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Repository", back_populates="wikis"
    )
    pages: Mapped[list["WikiPage"]] = relationship(
        "WikiPage", back_populates="wiki", cascade="all, delete-orphan"
    )
    modules: Mapped[list["Module"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Module", back_populates="wiki", cascade="all, delete-orphan"
    )


class WikiPage(Base, TimestampMixin):
    __tablename__ = "wiki_pages"
    __table_args__ = (UniqueConstraint("wiki_id", "slug", name="uq_wiki_page_slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    wiki_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("wikis.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    page_type: Mapped[PageType] = mapped_column(
        String(30), nullable=False, default=PageType.module
    )
    # JSONB structured content — sections, links, code examples
    content: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    # JSONB list of relative file paths that this page documents
    source_files: Mapped[Optional[list[str]]] = mapped_column(JSONB)
    commit_hash: Mapped[Optional[str]] = mapped_column(String(40))
    summary: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    wiki: Mapped[Wiki] = relationship("Wiki", back_populates="pages")
