"""add video_tasks table

Revision ID: a2b3c4d5e6f7
Revises: fcb43ab7b114
Create Date: 2026-04-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "fcb43ab7b114"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE taskstatus AS ENUM ('QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.create_table(
        "video_tasks",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column(
            "video_id", sa.String(36),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Configuration
        sa.Column("source_lang", sa.String(20), nullable=True),
        sa.Column("target_lang", sa.String(20), nullable=False, server_default="arb_Arab"),
        sa.Column("output_type", sa.String(50), nullable=False, server_default="fullDubbing"),
        sa.Column("num_beams", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("english_ratio_threshold", sa.Float(), nullable=False, server_default="0.5"),
        # Status
        sa.Column(
            "status",
            PgEnum(name="taskstatus", create_type=False),
            nullable=False,
            server_default="QUEUED",
        ),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        # STT output
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("stt_segments", sa.JSON(), nullable=True),
        sa.Column("stt_metadata", sa.JSON(), nullable=True),
        # NMT output
        sa.Column("translated_transcript", sa.Text(), nullable=True),
        # Combined segments (STT + NMT + TTS)
        sa.Column("segments", sa.JSON(), nullable=True),
        # TTS combined output
        sa.Column("combined_audio_key", sa.String(512), nullable=True),
        # Link to root job
        sa.Column(
            "root_job_id", sa.String(36),
            sa.ForeignKey("jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Timestamps
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )

    op.create_index("ix_video_tasks_video_id", "video_tasks", ["video_id"])
    op.create_index("ix_video_tasks_user_id", "video_tasks", ["user_id"])
    op.create_index("ix_video_tasks_status", "video_tasks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_video_tasks_status", table_name="video_tasks")
    op.drop_index("ix_video_tasks_user_id", table_name="video_tasks")
    op.drop_index("ix_video_tasks_video_id", table_name="video_tasks")
    op.drop_table("video_tasks")
    op.execute("DROP TYPE IF EXISTS taskstatus")
