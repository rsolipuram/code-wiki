"""add_branch_column

Revision ID: b3a1e7c52d91
Revises: f647086c8e6a
Create Date: 2026-02-28 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b3a1e7c52d91'
down_revision: Union[str, Sequence[str], None] = 'f647086c8e6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add branch column to repositories table."""
    op.add_column('repositories', sa.Column('branch', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Remove branch column from repositories table."""
    op.drop_column('repositories', 'branch')
