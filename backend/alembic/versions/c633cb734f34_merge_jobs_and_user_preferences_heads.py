"""merge_jobs_and_user_preferences_heads

Revision ID: c633cb734f34
Revises: a1b2c3d4e5f6, d4e6b1bc8db1
Create Date: 2026-04-10 10:24:21.433994

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c633cb734f34'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f6', 'd4e6b1bc8db1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
