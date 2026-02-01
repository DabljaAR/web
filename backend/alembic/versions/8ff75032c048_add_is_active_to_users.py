"""add is_active to users

Revision ID: 8ff75032c048
Revises: cb61867109a6
Create Date: 2026-01-29 19:55:20.772161

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8ff75032c048'
down_revision: Union[str, Sequence[str], None] = 'cb61867109a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'is_active')
