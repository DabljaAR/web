"""Progressive video merging models and data structures."""
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional
from pathlib import Path
from sqlalchemy import Column, String, Integer, Float, Text, JSON, TIMESTAMP, UUID, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from app.core.db import Base


class SegmentStatus(str, Enum):
    """Status values for progressive segment processing."""
    PENDING = "pending"
    NMT_PROCESSING = "nmt_processing" 
    TTS_PROCESSING = "tts_processing"
    READY_TO_MERGE = "ready_to_merge"
    MERGED = "merged"
    FAILED = "failed"


class ProgressiveSegment(Base):
    """SQLAlchemy model for tracking individual segment progression."""
    __tablename__ = "progressive_segments"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    job_id = Column(String(36), ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False)
    segment_id = Column(Integer, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default=SegmentStatus.PENDING.value)
    nmt_result = Column(JSON, nullable=True)
    tts_audio_key = Column(Text, nullable=True)
    video_inserted_at = Column(TIMESTAMP(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('job_id', 'segment_id', name='uq_progressive_segments_job_segment'),
        Index('idx_progressive_segments_job_status', 'job_id', 'status'),
        Index('idx_progressive_segments_timeline', 'job_id', 'start_time'),
    )


@dataclass
class SegmentInfo:
    """In-memory representation of a progressive segment."""
    segment_id: int
    start_time: float
    end_time: float
    status: SegmentStatus
    nmt_result: Optional[Dict] = None
    tts_audio_key: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class VideoTimeline:
    """In-memory representation of a progressive video timeline."""
    job_id: str
    video_id: str
    total_duration: float
    segments: Dict[int, SegmentInfo]
    current_video_path: Optional[Path] = None
    
    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage based on merged segments."""
        if not self.segments:
            return 0.0
        merged_count = sum(1 for s in self.segments.values() if s.status == SegmentStatus.MERGED)
        return (merged_count / len(self.segments)) * 100.0
    
    @property
    def ready_segments(self) -> List[SegmentInfo]:
        """Get segments ready to merge, sorted by timeline order."""
        ready = [s for s in self.segments.values() if s.status == SegmentStatus.READY_TO_MERGE]
        return sorted(ready, key=lambda x: x.start_time)
    
    @property
    def next_expected_segment_id(self) -> Optional[int]:
        """Get the next segment ID that should be processed in timeline order."""
        for seg_id in sorted(self.segments.keys()):
            if self.segments[seg_id].status not in [SegmentStatus.MERGED, SegmentStatus.FAILED]:
                return seg_id
        return None


@dataclass
class ProgressiveUpdateMessage:
    """Message structure for WebSocket progress updates."""
    type: str
    job_id: str
    segment_id: Optional[int] = None
    completion_percentage: Optional[float] = None
    current_video_url: Optional[str] = None
    status: Optional[str] = None
    timestamp: Optional[float] = None