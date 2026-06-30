"""merge_heads_google_id_and_processing_mode

Revision ID: a3a8276c0f9f
Revises: b8a7c9d1e2f3, e9ab12cd34ef
Create Date: 2026-06-29 20:09:05.663401

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3a8276c0f9f'
down_revision: Union[str, Sequence[str], None] = ('b8a7c9d1e2f3', 'e9ab12cd34ef')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
