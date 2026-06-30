"""Add google_id column to users table

Revision ID: b8a7c9d1e2f3
Revises: d298f1b34c73
Create Date: 2026-06-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8a7c9d1e2f3'
down_revision: Union[str, Sequence[str], None] = 'd298f1b34c73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'users',
        sa.Column('google_id', sa.String(255), nullable=True),
    )
    op.create_index(op.f('ix_users_google_id'), 'users', ['google_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_users_google_id'), table_name='users', if_exists=True)
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS google_id")
