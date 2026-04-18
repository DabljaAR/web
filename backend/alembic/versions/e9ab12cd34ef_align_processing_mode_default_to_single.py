"""align processing_mode default to single

Revision ID: e9ab12cd34ef
Revises: f4d5e6a7b8c9
Create Date: 2026-04-18 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e9ab12cd34ef"
down_revision: Union[str, Sequence[str], None] = "f4d5e6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep old rows semantically consistent with the new mode contract.
    op.execute("UPDATE video_tasks SET processing_mode = 'stt_focused' WHERE processing_mode = 'segmented'")
    op.alter_column(
        "video_tasks",
        "processing_mode",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="single",
    )


def downgrade() -> None:
    op.alter_column(
        "video_tasks",
        "processing_mode",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="segmented",
    )
    op.execute("UPDATE video_tasks SET processing_mode = 'segmented' WHERE processing_mode = 'stt_focused'")
