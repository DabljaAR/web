"""
TranscriptionService — thin client wrapper over the STT microservice.

All transcription logic lives in ``stt-service``.  This class:
  - Proxies sync file-upload requests to the microservice HTTP endpoint.
  - Creates Job rows and publishes ``job.created`` to RabbitMQ for async requests.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional

import httpx
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.jobs.models import Job, JobStatus, JobType
from app.media.models import Video
from app.shared.processing_mode import resolve_processing_mode
from app.shared.rabbitmq import publish_job_created
from app.stt.schema import (
    TranscriptionMetadata,
    TranscriptionResponse,
    TranscriptionSegment,
)

logger = logging.getLogger(__name__)

_MICROSERVICE_TIMEOUT = 300.0  # seconds — long enough for large files


class TranscriptionService:
    """Facade over the STT microservice.  One instance per request (DB session scoped)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Sync transcription — HTTP proxy to STT microservice
    # ------------------------------------------------------------------

    async def transcribe_file(
        self,
        file: UploadFile,
        language: Optional[str] = None,
    ) -> TranscriptionResponse:
        """Forward a raw file upload to the STT microservice and return the result."""
        url = f"{settings.STT_SERVICE_URL}/transcribe"
        params = {"language": language} if language else {}

        content = await file.read()
        try:
            async with httpx.AsyncClient(timeout=_MICROSERVICE_TIMEOUT) as client:
                response = await client.post(
                    url,
                    files={"file": (file.filename or "upload", content, file.content_type or "application/octet-stream")},
                    params=params,
                )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text or str(exc)
            raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"STT microservice unreachable: {exc}",
            ) from exc

        data = response.json()
        return TranscriptionResponse(
            transcript=data["transcript"],
            segments=[TranscriptionSegment(**s) for s in data["segments"]],
            metadata=TranscriptionMetadata(**data["metadata"]),
        )

    # ------------------------------------------------------------------
    # Async transcription — creates Job row + fires RabbitMQ event
    # ------------------------------------------------------------------

    async def submit_async_transcription(
        self,
        file_key: str,
        user_id: int,
        language: Optional[str] = None,
        video_id: Optional[str] = None,
        target_lang: str = "arb_Arab",
    ) -> Job:
        """Create a Job record and publish ``job.created`` to RabbitMQ.

        The orchestrator receives the event, marks the job PROCESSING, and
        dispatches it to the STT microservice via ``job.start.stt``.
        """
        if video_id:
            result = await self.db.execute(select(Video).where(Video.id == video_id))
            video: Optional[Video] = result.scalar_one_or_none()
            if not video:
                raise HTTPException(status_code=404, detail=f"Video {video_id} not found.")
            if video.user_id != user_id:
                raise HTTPException(status_code=403, detail="Access denied.")

        # Return existing active job to prevent duplicates
        existing = await self.db.execute(
            select(Job).where(
                Job.video_id == video_id,
                Job.job_type == JobType.STT_TRANSCRIBE,
                Job.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING]),
            )
        )
        active = existing.scalars().first()
        if active:
            logger.info("[STT] Returning existing active job %s for video %s", active.id, video_id)
            return active

        output_type = "fullDubbing"
        processing_mode = resolve_processing_mode(output_type)

        job = Job(
            id=str(uuid.uuid4()),
            video_id=video_id,
            user_id=user_id,
            job_type=JobType.STT_TRANSCRIBE,
            status=JobStatus.QUEUED,
            progress=0.0,
            input_data={
                "video_id": video_id,
                "language": language,
                "target_lang": target_lang,
                "output_type": output_type,
                "processing_mode": processing_mode,
            },
            retry_count=0,
            max_retries=3,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)

        published = publish_job_created(job.id)
        if not published:
            logger.warning("[STT] RabbitMQ publish failed for job %s; job is QUEUED in DB", job.id)

        logger.info("[STT] Job %s queued | video=%s | language=%s | published=%s", job.id, video_id, language, published)
        return job

