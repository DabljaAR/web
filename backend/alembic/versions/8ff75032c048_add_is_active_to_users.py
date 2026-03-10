"""Make users.is_active NOT NULL with default True

Revision ID: 8ff75032c048
Revises: f1a2b3c4d5e6
Create Date: 2026-02-20 00:03:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8ff75032c048'
down_revision = 'cb61867109a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Back-fill any NULLs before tightening the constraint.
    op.execute("UPDATE users SET is_active = TRUE WHERE is_active IS NULL")
    op.alter_column(
        'users',
        'is_active',
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text('true'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'users',
        'is_active',
        existing_type=sa.Boolean(),
        nullable=True,
        server_default=None,
    )
