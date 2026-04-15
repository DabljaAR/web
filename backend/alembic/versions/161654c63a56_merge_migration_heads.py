"""merge_migration_heads

Revision ID: 161654c63a56
Revises: a1b2c3d4e5f6, c2d4e6f8a0b1, d4e6b1bc8db1
Create Date: 2026-04-08 00:34:52.347600

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '161654c63a56'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f6', 'c2d4e6f8a0b1', 'd4e6b1bc8db1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
