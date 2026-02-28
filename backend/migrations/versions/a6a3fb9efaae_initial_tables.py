"""initial_tables

Revision ID: a6a3fb9efaae
Revises:
Create Date: 2026-02-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a6a3fb9efaae"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # repositories
    op.create_table(
        "repositories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("url", sa.String(2048), nullable=False, unique=True),
        sa.Column("name", sa.String(255)),
        sa.Column("description", sa.Text()),
        sa.Column("primary_language", sa.String(50)),
        sa.Column(
            "status",
            sa.Enum("pending", "analyzing", "ready", "error", name="repositorystatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text()),
        sa.Column("last_analyzed_commit", sa.String(40)),
        sa.Column("file_count", sa.Integer()),
        sa.Column("line_count", sa.Integer()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # wikis
    op.create_table(
        "wikis",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "repository_id",
            sa.String(36),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("module_count", sa.Integer(), server_default="0"),
        sa.Column("page_count", sa.Integer(), server_default="0"),
        sa.Column("version", sa.Integer(), server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # wiki_pages
    op.create_table(
        "wiki_pages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "wiki_id",
            sa.String(36),
            sa.ForeignKey("wikis.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("page_type", sa.String(30), nullable=False, server_default="module"),
        sa.Column("content", postgresql.JSONB()),
        sa.Column("commit_hash", sa.String(40)),
        sa.Column("summary", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("wiki_id", "slug", name="uq_wiki_page_slug"),
    )

    # modules
    op.create_table(
        "modules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "wiki_id",
            sa.String(36),
            sa.ForeignKey("wikis.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("detection_confidence", sa.Float(), server_default="1.0"),
        sa.Column("file_paths", postgresql.JSONB()),
        sa.Column("file_count", sa.Integer(), server_default="0"),
        sa.Column("line_count", sa.Integer(), server_default="0"),
        sa.Column("dependency_module_ids", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # code_entities
    op.create_table(
        "code_entities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "module_id",
            sa.String(36),
            sa.ForeignKey("modules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("qualified_name", sa.String(1024), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("file_path", sa.String(1024)),
        sa.Column("line_start", sa.Integer()),
        sa.Column("line_end", sa.Integer()),
        sa.Column("signature", sa.Text()),
        sa.Column("docstring", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("interestingness_score", sa.Float(), server_default="0.0"),
        sa.Column("entity_metadata", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("module_id", "qualified_name", name="uq_entity_qualified_name"),
    )

    # chat_conversations
    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "repository_id",
            sa.String(36),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(512)),
        sa.Column("messages", postgresql.JSONB(), server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # update_events
    op.create_table(
        "update_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "repository_id",
            sa.String(36),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("commit_hash", sa.String(40), nullable=False),
        sa.Column("changed_files", postgresql.JSONB()),
        sa.Column("affected_module_ids", postgresql.JSONB()),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("update_events")
    op.drop_table("chat_conversations")
    op.drop_table("code_entities")
    op.drop_table("modules")
    op.drop_table("wiki_pages")
    op.drop_table("wikis")
    op.drop_table("repositories")
    op.execute("DROP TYPE IF EXISTS repositorystatus")
