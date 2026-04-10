"""align_languages_enum_values

Revision ID: fcb43ab7b114
Revises: c633cb734f34
Create Date: 2026-04-10 10:30:29.351226

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'fcb43ab7b114'
down_revision: Union[str, Sequence[str], None] = 'c633cb734f34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TYPE languages_enum_new AS ENUM (
            'en', 'ar', 'es', 'fr', 'de', 'pt', 'it', 'ru', 'zh', 'ja', 'ko'
        )
        """
    )
    op.execute("ALTER TABLE users ALTER COLUMN preferred_language DROP DEFAULT")
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN preferred_language
        TYPE languages_enum_new
        USING (
            CASE preferred_language::text
                WHEN 'ENGLISH' THEN 'en'::languages_enum_new
                WHEN 'ARABIC' THEN 'ar'::languages_enum_new
                WHEN 'en' THEN 'en'::languages_enum_new
                WHEN 'ar' THEN 'ar'::languages_enum_new
                WHEN 'es' THEN 'es'::languages_enum_new
                WHEN 'fr' THEN 'fr'::languages_enum_new
                WHEN 'de' THEN 'de'::languages_enum_new
                WHEN 'pt' THEN 'pt'::languages_enum_new
                WHEN 'it' THEN 'it'::languages_enum_new
                WHEN 'ru' THEN 'ru'::languages_enum_new
                WHEN 'zh' THEN 'zh'::languages_enum_new
                WHEN 'ja' THEN 'ja'::languages_enum_new
                WHEN 'ko' THEN 'ko'::languages_enum_new
                ELSE 'en'::languages_enum_new
            END
        )
        """
    )
    op.execute("DROP TYPE languages_enum")
    op.execute("ALTER TYPE languages_enum_new RENAME TO languages_enum")
    op.execute("ALTER TABLE users ALTER COLUMN preferred_language SET DEFAULT 'en'::languages_enum")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("CREATE TYPE languages_enum_old AS ENUM ('ENGLISH', 'ARABIC')")
    op.execute("ALTER TABLE users ALTER COLUMN preferred_language DROP DEFAULT")
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN preferred_language
        TYPE languages_enum_old
        USING (
            CASE preferred_language::text
                WHEN 'ar' THEN 'ARABIC'::languages_enum_old
                ELSE 'ENGLISH'::languages_enum_old
            END
        )
        """
    )
    op.execute("DROP TYPE languages_enum")
    op.execute("ALTER TYPE languages_enum_old RENAME TO languages_enum")
    op.execute("ALTER TABLE users ALTER COLUMN preferred_language SET DEFAULT 'ENGLISH'::languages_enum")
