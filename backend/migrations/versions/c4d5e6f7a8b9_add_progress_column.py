"""add_progress_column

Revision ID: c4d5e6f7a8b9
Revises: b3a1e7c52d91
Create Date: 2026-02-28 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'b3a1e7c52d91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add progress JSONB column to repositories table."""
    op.add_column('repositories', sa.Column('progress', JSONB(), nullable=True))


def downgrade() -> None:
    """Remove progress column from repositories table."""
    op.drop_column('repositories', 'progress')
