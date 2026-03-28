"""Module and CodeEntity SQLAlchemy models."""

import enum
from typing import Any, Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, new_uuid


class EntityType(str, enum.Enum):
    function = "function"
    method = "method"
    class_ = "class"
    module = "module"
    interface = "interface"
    variable = "variable"


class Module(Base, TimestampMixin):
    __tablename__ = "modules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    wiki_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("wikis.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # Confidence 0.0-1.0 for automatic module detection
    detection_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    file_paths: Mapped[Optional[list[str]]] = mapped_column(JSONB)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    line_count: Mapped[int] = mapped_column(Integer, default=0)
    # IDs of modules this module depends on
    dependency_module_ids: Mapped[Optional[list[str]]] = mapped_column(JSONB)

    # Relationships
    wiki: Mapped["Wiki"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Wiki", back_populates="modules"
    )
    entities: Mapped[list["CodeEntity"]] = relationship(
        "CodeEntity", back_populates="module", cascade="all, delete-orphan"
    )


class CodeEntity(Base, TimestampMixin):
    __tablename__ = "code_entities"
    __table_args__ = (
        UniqueConstraint("module_id", "qualified_name", name="uq_entity_qualified_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    module_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("modules.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Full dotted path e.g. src.auth.login.authenticate_user
    qualified_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    entity_type: Mapped[EntityType] = mapped_column(String(20), nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(1024))
    line_start: Mapped[Optional[int]] = mapped_column(Integer)
    line_end: Mapped[Optional[int]] = mapped_column(Integer)
    signature: Mapped[Optional[str]] = mapped_column(Text)
    docstring: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # Interestingness score 0.0-1.0 from StructuralAnalyst
    interestingness_score: Mapped[float] = mapped_column(Float, default=0.0)
    # Extra data (parameters, return type, decorators, etc.)
    entity_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)

    # Relationships
    module: Mapped[Module] = relationship("Module", back_populates="entities")
