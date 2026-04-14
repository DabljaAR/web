"""add processing_mode to video_tasks

Revision ID: b5c6d7e8f901
Revises: a2b3c4d5e6f7
Create Date: 2026-04-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b5c6d7e8f901"
down_revision: Union[str, Sequence[str], None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "video_tasks",
        sa.Column("processing_mode", sa.String(length=20), nullable=False, server_default="segmented"),
    )


def downgrade() -> None:
    op.drop_column("video_tasks", "processing_mode")
