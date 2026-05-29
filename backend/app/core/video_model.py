"""
SQLAlchemy ORM stub for the `videos` table.

The table is owned and written by the Rust media-service; this model exists
solely so that Alembic autogenerate can see the table and won't emit DROP TABLE
commands during migrations.  All actual video CRUD goes through MediaServiceClient.
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum, JSON

from app.core.db import Base


class Video(Base):
    __tablename__ = "videos"

    id = sa.Column(sa.String(36), primary_key=True, nullable=False)
    user_id = sa.Column(
        sa.Integer(),
        sa.ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = sa.Column(sa.String(255), nullable=False)
    original_filename = sa.Column(sa.String(255), nullable=False)
    file_path = sa.Column(sa.String(512), nullable=False)
    thumbnail_path = sa.Column(sa.String(512), nullable=True)
    audio_path = sa.Column(sa.String(512), nullable=True)
    duration = sa.Column(sa.Float(), nullable=True)
    width = sa.Column(sa.Integer(), nullable=True)
    height = sa.Column(sa.Integer(), nullable=True)
    size_bytes = sa.Column(sa.BigInteger(), nullable=True)
    format = sa.Column(sa.String(50), nullable=True)
    codec = sa.Column(sa.String(50), nullable=True)
    frame_rate = sa.Column(sa.Float(), nullable=True)
    status = sa.Column(
        PgEnum(name="videostatus", create_type=False),
        nullable=False,
        server_default="PENDING",
    )
    error_message = sa.Column(sa.Text(), nullable=True)
    created_at = sa.Column(
        sa.DateTime(), nullable=False, server_default=sa.text("now()")
    )
    updated_at = sa.Column(
        sa.DateTime(), nullable=False, server_default=sa.text("now()")
    )
    media_type = sa.Column(
        PgEnum(name="mediatype", create_type=False),
        nullable=False,
        server_default="VIDEO",
    )
    dubbed_video_path = sa.Column(sa.String(512), nullable=True)
    dubbing_metadata = sa.Column(JSON, nullable=True)
