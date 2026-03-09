"""Add media_type to Video

Revision ID: 4a3c6e5f0f37
Revises: 036f31c8fe71
Create Date: 2026-02-13 20:35:17.038845

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum


# revision identifiers, used by Alembic.
revision: str = '4a3c6e5f0f37'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE mediatype AS ENUM ('VIDEO', 'AUDIO', 'TEXT');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.add_column(
        'videos',
        sa.Column(
            'media_type',
            PgEnum(name='mediatype', create_type=False),
            nullable=False,
            server_default='VIDEO',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('videos', 'media_type')
    op.execute('DROP TYPE IF EXISTS mediatype')

