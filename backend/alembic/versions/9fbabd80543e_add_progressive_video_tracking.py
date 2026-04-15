"""add_progressive_video_tracking

Revision ID: 9fbabd80543e
Revises: 161654c63a56
Create Date: 2026-04-08 00:35:01.139974

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9fbabd80543e'
down_revision: Union[str, Sequence[str], None] = '161654c63a56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add progressive video tracking capabilities."""
    
    # Add progressive tracking columns to jobs table
    op.add_column('jobs', sa.Column('segments_total', sa.Integer(), default=0))
    op.add_column('jobs', sa.Column('segments_completed', sa.Integer(), default=0))
    op.add_column('jobs', sa.Column('current_video_url', sa.Text(), nullable=True))
    op.add_column('jobs', sa.Column('merge_timeline', sa.JSON(), nullable=True))
    
    # Create progressive_segments table for detailed segment tracking
    op.create_table('progressive_segments',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('segment_id', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.Float(), nullable=False),
        sa.Column('end_time', sa.Float(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, default='pending'),
        sa.Column('nmt_result', sa.JSON(), nullable=True),
        sa.Column('tts_audio_key', sa.Text(), nullable=True),
        sa.Column('video_inserted_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('job_id', 'segment_id', name='uq_progressive_segments_job_segment')
    )
    
    # Create indexes for efficient queries
    op.create_index('idx_progressive_segments_job_status', 'progressive_segments', ['job_id', 'status'])
    op.create_index('idx_progressive_segments_timeline', 'progressive_segments', ['job_id', 'start_time'])


def downgrade() -> None:
    """Remove progressive video tracking capabilities."""
    
    # Drop indexes
    op.drop_index('idx_progressive_segments_timeline', table_name='progressive_segments')
    op.drop_index('idx_progressive_segments_job_status', table_name='progressive_segments')
    
    # Drop progressive_segments table
    op.drop_table('progressive_segments')
    
    # Remove columns from jobs table
    op.drop_column('jobs', 'merge_timeline')
    op.drop_column('jobs', 'current_video_url')
    op.drop_column('jobs', 'segments_completed')
    op.drop_column('jobs', 'segments_total')
