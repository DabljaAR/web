"""merge_progressive_and_video_task_heads

Revision ID: f4d5e6a7b8c9
Revises: 7407083b93d0, b5c6d7e8f901
Create Date: 2026-04-16 00:33:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "f4d5e6a7b8c9"
down_revision: Union[str, Sequence[str], None] = ("7407083b93d0", "b5c6d7e8f901")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
