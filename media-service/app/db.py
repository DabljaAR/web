import json
import logging
from typing import Optional, Any
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def init_db(database_url: str) -> None:
    global _engine, _SessionLocal
    _engine = create_async_engine(database_url, pool_size=5, max_overflow=10)
    _SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


def get_session() -> AsyncSession:
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized — call init_db() first")
    return _SessionLocal()


async def get_video(session: AsyncSession, video_id: str) -> Optional[dict]:
    result = await session.execute(
        text("""
            SELECT
                id, user_id, title, original_filename,
                media_type::TEXT AS media_type,
                file_path, thumbnail_path, audio_path,
                dubbed_video_path, dubbing_metadata,
                duration, width, height, size_bytes,
                format, codec, frame_rate,
                status::TEXT AS status,
                error_message, created_at, updated_at
            FROM videos WHERE id = :video_id
        """),
        {"video_id": video_id},
    )
    row = result.mappings().first()
    if row is None:
        return None
    data = dict(row)
    for key in ("created_at", "updated_at"):
        if isinstance(data.get(key), datetime):
            data[key] = data[key].isoformat()
    return data


async def patch_video_paths(
    session: AsyncSession,
    video_id: str,
    dubbed_video_path: Optional[str],
    dubbing_metadata: Optional[dict],
    audio_path: Optional[str],
    thumbnail_path: Optional[str],
    file_path: Optional[str],
) -> int:
    merged_metadata: Optional[str] = None
    if dubbing_metadata is not None:
        fetch = await session.execute(
            text("SELECT dubbing_metadata FROM videos WHERE id = :id"),
            {"id": video_id},
        )
        row = fetch.mappings().first()
        if row is None:
            return 0
        existing = row["dubbing_metadata"] or {}
        merged_metadata = json.dumps({**existing, **dubbing_metadata})

    result = await session.execute(
        text("""
            UPDATE videos SET
                dubbed_video_path = COALESCE(:dubbed_video_path, dubbed_video_path),
                dubbing_metadata  = CASE
                    WHEN :merged_metadata IS NOT NULL
                    THEN CAST(:merged_metadata AS json)
                    ELSE dubbing_metadata
                END,
                audio_path        = COALESCE(:audio_path, audio_path),
                thumbnail_path    = COALESCE(:thumbnail_path, thumbnail_path),
                file_path         = COALESCE(:file_path, file_path),
                updated_at        = NOW()
            WHERE id = :video_id
        """),
        {
            "video_id": video_id,
            "dubbed_video_path": dubbed_video_path,
            "merged_metadata": merged_metadata,
            "audio_path": audio_path,
            "thumbnail_path": thumbnail_path,
            "file_path": file_path,
        },
    )
    await session.commit()
    return result.rowcount


async def patch_video_status(
    session: AsyncSession,
    video_id: str,
    status: str,
    error_message: Optional[str],
    duration: Optional[float],
    width: Optional[int],
    height: Optional[int],
    size_bytes: Optional[int],
    format: Optional[str],
    codec: Optional[str],
    frame_rate: Optional[float],
) -> int:
    result = await session.execute(
        text("""
            UPDATE videos SET
                status        = :status::videostatus,
                error_message = COALESCE(:error_message, error_message),
                duration      = COALESCE(:duration, duration),
                width         = COALESCE(:width, width),
                height        = COALESCE(:height, height),
                size_bytes    = COALESCE(:size_bytes, size_bytes),
                format        = COALESCE(:format, format),
                codec         = COALESCE(:codec, codec),
                frame_rate    = COALESCE(:frame_rate, frame_rate),
                updated_at    = NOW()
            WHERE id = :video_id
        """),
        {
            "video_id": video_id,
            "status": status,
            "error_message": error_message,
            "duration": duration,
            "width": width,
            "height": height,
            "size_bytes": size_bytes,
            "format": format,
            "codec": codec,
            "frame_rate": frame_rate,
        },
    )
    await session.commit()
    return result.rowcount
