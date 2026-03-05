"""Create videos table

Revision ID: e1f2a3b4c5d6
Revises: 036f31c8fe71
Create Date: 2026-02-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = '036f31c8fe71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Use a PL/pgSQL DO-block so the type is created idempotently without
    # going through SQLAlchemy's event system (which ignores create_type=False
    # in some 2.x releases and always re-emits CREATE TYPE during create_table).
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE videostatus AS ENUM
                ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # PgEnum with create_type=False is a bare type reference — it never
    # attempts to emit CREATE TYPE regardless of SQLAlchemy version.
    videostatus_col = PgEnum(name='videostatus', create_type=False)

    op.create_table(
        'videos',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey('users.user_id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(512), nullable=False),
        sa.Column('thumbnail_path', sa.String(512), nullable=True),
        sa.Column('audio_path', sa.String(512), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('format', sa.String(50), nullable=True),
        sa.Column('codec', sa.String(50), nullable=True),
        sa.Column('frame_rate', sa.Float(), nullable=True),
        sa.Column(
            'status',
            videostatus_col,
            nullable=False,
            server_default='PENDING',
        ),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('now()'),
        ),
    )
    op.create_index('ix_videos_user_id', 'videos', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_videos_user_id', table_name='videos')
    op.drop_table('videos')
    op.execute('DROP TYPE IF EXISTS videostatus')
