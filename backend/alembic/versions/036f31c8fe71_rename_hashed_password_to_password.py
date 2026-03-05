"""rename_hashed_password_to_password

Revision ID: 036f31c8fe71
Revises: 8ff75032c048
Create Date: 2026-02-08 20:37:38.022982

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '036f31c8fe71'
down_revision: Union[str, Sequence[str], None] = 'cb61867109a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('users', 'hashed_password', new_column_name='password')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('users', 'password', new_column_name='hashed_password')
