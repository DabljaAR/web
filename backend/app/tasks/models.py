"""VideoTask — single source-of-truth for one processing pipeline run.

One VideoTask is created per user request (upload / reprocess).
It stores both the configuration chosen by the user and the merged
output produced by each pipeline stage (STT → NMT → TTS).

The individual Job rows in the `jobs` table still exist for per-stage
progress tracking, but the final, queryable result lives here.
"""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, DateTime, ForeignKey, Text, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Enum as SQLEnum

from app.core.db import Base


class TaskStatus(str, enum.Enum):
    QUEUED      = "QUEUED"
    PROCESSING  = "PROCESSING"
    COMPLETED   = "COMPLETED"
    FAILED      = "FAILED"


class VideoTask(Base):
    __tablename__ = "video_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # ── Ownership ────────────────────────────────────────────────────────────
    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("videos.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # ── Configuration (set at creation, never mutated) ───────────────────────
    source_lang: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)   # None / "auto" = detect
    target_lang: Mapped[str]           = mapped_column(String(20), nullable=False, default="arb_Arab")
    output_type: Mapped[str]           = mapped_column(String(50), nullable=False, default="fullDubbing")
    num_beams: Mapped[int]             = mapped_column(Integer,    nullable=False, default=5)
    english_ratio_threshold: Mapped[float] = mapped_column(Float,  nullable=False, default=0.5)

    # ── Overall status ───────────────────────────────────────────────────────
    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus, name="taskstatus"),
        nullable=False, default=TaskStatus.QUEUED,
    )
    progress: Mapped[float]             = mapped_column(Float, nullable=False, default=0.0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── STT output ───────────────────────────────────────────────────────────
    transcript: Mapped[Optional[str]]    = mapped_column(Text, nullable=True)
    stt_segments: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # [{start, end, text}, ...]
    stt_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # ── NMT output ───────────────────────────────────────────────────────────
    translated_transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Merged segments (STT + NMT + TTS combined) ───────────────────────────
    # Each element: {start, end, original_text, translated_text, tts_key, audio_url}
    segments: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # ── TTS combined output ──────────────────────────────────────────────────
    # MinIO key for the single merged audio file produced by tts_combine_results
    combined_audio_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # ── Link to the root STT job that started this pipeline ──────────────────
    root_job_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True,
    )

    # ── Timestamps ───────────────────────────────────────────────────────────
    created_at: Mapped[datetime]          = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime]          = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<VideoTask id={self.id} video={self.video_id} status={self.status}>"
