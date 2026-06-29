"""
TTS Service — standalone synthesis with Job tracking.

Pipeline TTS runs via tts-service RabbitMQ consumer. This module proxies
POST /api/tts/synthesize to tts-service HTTP (TTS_SERVICE_URL).
"""

import logging
import uuid
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)


class TTSService:
    """Proxy standalone TTS requests to the tts-service microservice."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def submit_tts(
        self,
        text: str,
        job_id: Optional[str] = None,
        user_id: Optional[int] = None,
        video_id: Optional[int] = None,
        ref_audio_path: Optional[str] = None,
        ref_text: Optional[str] = None,
        speed: Optional[float] = None,
        cfg_strength: Optional[float] = None,
        nfe_step: Optional[int] = None,
        sway_sampling_coef: Optional[float] = None,
        target_rms: Optional[float] = None,
        seed: Optional[int] = None,
        target_lang: str = "arb_Arab",
        upload_to_minio: bool = False,
        minio_key: Optional[str] = None,
    ) -> str:
        """Submit TTS synthesis via tts-service HTTP API. Returns job_id."""
        job_id = job_id or str(uuid.uuid4())
        payload = {
            "text": text,
            "job_id": job_id,
            "ref_audio_path": ref_audio_path,
            "ref_text": ref_text,
            "speed": speed,
            "cfg_strength": cfg_strength,
            "nfe_step": nfe_step,
            "sway_sampling_coef": sway_sampling_coef,
            "target_rms": target_rms,
            "seed": seed,
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        url = f"{settings.TTS_SERVICE_URL.rstrip('/')}/synthesize"
        logger.info("[TTS Service] Proxying synthesis to %s job=%s", url, job_id)

        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500] if exc.response else str(exc)
            logger.error("[TTS Service] tts-service HTTP error: %s", detail)
            raise RuntimeError(f"TTS service error: {detail}") from exc
        except httpx.RequestError as exc:
            logger.error("[TTS Service] tts-service unreachable: %s", exc)
            raise RuntimeError(f"TTS service unreachable at {url}") from exc

        returned_id = data.get("job_id") or job_id
        logger.info("[TTS Service] Synthesis complete job=%s status=%s", returned_id, data.get("status"))
        return returned_id

    async def get_job_status(self, job_id: str) -> Optional[dict]:
        """Get job status — prefer tts-service, fall back to local DB."""
        url = f"{settings.TTS_SERVICE_URL.rstrip('/')}/status/{job_id}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url)
                if resp.status_code == 404:
                    pass
                else:
                    resp.raise_for_status()
                    row = resp.json()
                    return {
                        "job_id": row.get("job_id", job_id),
                        "status": row.get("status"),
                        "video_id": None,
                        "output_data": row.get("output_data"),
                        "error_message": row.get("error_message"),
                        "created_at": row.get("created_at"),
                        "completed_at": row.get("completed_at"),
                    }
        except Exception as exc:
            logger.debug("[TTS Service] tts-service status fallback: %s", exc)

        from app.jobs.service import JobService

        job_service = JobService(self.db)
        job = await job_service.get_job(job_id)
        if not job:
            return None

        return {
            "job_id": job.id,
            "status": job.status.value,
            "video_id": job.video_id,
            "output_data": job.output_data,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

    def get_health(self) -> dict:
        """Health from tts-service /health/model when available."""
        url = f"{settings.TTS_SERVICE_URL.rstrip('/')}/health/model"
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "status": "healthy" if data.get("model_loaded") else "starting",
                        "model_loaded": data.get("model_loaded", False),
                        "device": data.get("device", "unknown"),
                        "model": "SILMA-TTS",
                        "version": "1.0.0",
                        "proxy": "tts-service",
                    }
        except Exception as exc:
            logger.warning("[TTS Service] tts-service health check failed: %s", exc)

        return {
            "status": "degraded",
            "model_loaded": False,
            "device": "unknown",
            "model": "SILMA-TTS",
            "version": "1.0.0",
            "proxy": "tts-service",
            "error": "tts-service unreachable",
        }
