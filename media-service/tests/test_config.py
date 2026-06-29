"""Tests for media-service database URL normalization."""
from app.config import Settings


def test_sqlalchemy_url_maps_psycopg2_to_asyncpg():
    cfg = Settings(
        DATABASE_URL="postgresql+psycopg2://postgres:secret@postgres:5432/dabljaar"
    )
    assert cfg.sqlalchemy_url == (
        "postgresql+asyncpg://postgres:secret@postgres:5432/dabljaar"
    )
    assert cfg.sync_db_url == (
        "postgresql+psycopg2://postgres:secret@postgres:5432/dabljaar"
    )


def test_sqlalchemy_url_maps_plain_postgresql_to_asyncpg():
    cfg = Settings(DATABASE_URL="postgresql://postgres:secret@localhost:5432/dabljaar")
    assert cfg.sqlalchemy_url == (
        "postgresql+asyncpg://postgres:secret@localhost:5432/dabljaar"
    )


def test_sync_db_url_maps_asyncpg_to_psycopg2():
    cfg = Settings(
        DATABASE_URL="postgresql+asyncpg://postgres:secret@postgres:5432/dabljaar"
    )
    assert cfg.sync_db_url == (
        "postgresql+psycopg2://postgres:secret@postgres:5432/dabljaar"
    )
