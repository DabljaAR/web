import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base

class TranslationStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Translation(Base):
    __tablename__ = "translations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True) # UUID
    video_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    
    source_lang: Mapped[str] = mapped_column(String(20), nullable=False) # e.g. "eng_Latn"
    target_lang: Mapped[str] = mapped_column(String(20), nullable=False) # e.g. "arb_Arab"
    
    # Storage paths for the .txt files
    source_text_path: Mapped[str] = mapped_column(String(512), nullable=False)
    translated_text_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    status: Mapped[TranslationStatus] = mapped_column(SQLEnum(TranslationStatus), default=TranslationStatus.PENDING, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    video: Mapped["Video"] = relationship("Video", back_populates="translations")
    user: Mapped["User"] = relationship("User") # Assuming User model exists in another module

    def __repr__(self):
        return f"<Translation {self.id} status={self.status}>"
