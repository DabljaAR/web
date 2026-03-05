"""Merge branches: add_media_type_to_video and increase_avatar_url_length

Revision ID: a73bb00612a0
Revises: 4a3c6e5f0f37, d298f1b34c73
Create Date: 2026-02-20 00:01:00.000000

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'a73bb00612a0'
down_revision: Union[str, Sequence[str], None] = ('4a3c6e5f0f37', 'd298f1b34c73')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
