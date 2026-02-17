"""Increase avatar_url length

Revision ID: d298f1b34c73
Revises: 4a3c6e5f0f37
Create Date: 2026-02-17 22:47:44.726670

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd298f1b34c73'
down_revision: Union[str, Sequence[str], None] = '4a3c6e5f0f37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('users', 'avatar_url',
               existing_type=sa.VARCHAR(length=255),
               type_=sa.Text(),
               existing_nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('users', 'avatar_url',
               existing_type=sa.Text(),
               type_=sa.VARCHAR(length=255),
               existing_nullable=True)
