"""add combined_audio_key to video_tasks

Revision ID: c1d2e3f4a5b6
Revises: a1b2c3d4e5f6, b1c2d3e4f5a6
Create Date: 2026-04-10

"""
from alembic import op
import sqlalchemy as sa

revision = 'c1d2e3f4a5b6'
down_revision = ('a1b2c3d4e5f6', 'b1c2d3e4f5a6')
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'video_tasks',
        sa.Column('combined_audio_key', sa.String(512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('video_tasks', 'combined_audio_key')
