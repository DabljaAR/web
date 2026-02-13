"""Add media_type to Video

Revision ID: 4a3c6e5f0f37
Revises: 036f31c8fe71
Create Date: 2026-02-13 20:35:17.038845

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a3c6e5f0f37'
down_revision: Union[str, Sequence[str], None] = '036f31c8fe71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create the enum type first
    mediatype = sa.Enum('VIDEO', 'AUDIO', 'TEXT', name='mediatype')
    mediatype.create(op.get_bind(), checkfirst=True)
    
    # Add the column using the enum type
    op.add_column('videos', sa.Column('media_type', mediatype, nullable=False, server_default='VIDEO'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('videos', 'media_type')
    mediatype = sa.Enum('VIDEO', 'AUDIO', 'TEXT', name='mediatype')
    mediatype.drop(op.get_bind(), checkfirst=True)
