"""add dubbing fields to videos

Revision ID: c2d4e6f8a0b1
Revises: f1a2b3c4d5e6
Create Date: 2026-04-07 19:57:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c2d4e6f8a0b1'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add dubbed_video_path column
    op.add_column('videos', sa.Column('dubbed_video_path', sa.String(length=512), nullable=True))
    
    # Add dubbing_metadata JSON column
    op.add_column('videos', sa.Column('dubbing_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    # Remove dubbing_metadata column
    op.drop_column('videos', 'dubbing_metadata')
    
    # Remove dubbed_video_path column
    op.drop_column('videos', 'dubbed_video_path')
