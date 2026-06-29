"""HTTP routes for standalone TTS synthesis (non-pipeline).

POST /synthesize      — sync TTS synthesis, returns audio_url + job_id
GET  /status/{job_id} — query job from DB
GET  /jobs/{job_id}   — job detail
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.config import settings
from app.model import _tts as _tts_model
from app.storage import upload_wav
from dablja_worker import make_engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["TTS"])


# ── schemas ──────────────────────────────────────────────────────────────────


class TTSRequest(BaseModel):
    text: str = Field(..., description="Arabic text to synthesize")
    ref_audio_path: Optional[str] = Field(default=None, description="Reference audio path for voice cloning")
    ref_text: Optional[str] = Field(default=None, description="Transcript of reference audio")
    speed: Optional[float] = Field(default=None)
    cfg_strength: Optional[float] = Field(default=None)
    nfe_step: Optional[int] = Field(default=None)
    sway_sampling_coef: Optional[float] = Field(default=None)
    target_rms: Optional[float] = Field(default=None)
    seed: Optional[int] = Field(default=None)
    job_id: Optional[str] = Field(default=None)

    class Config:
        json_schema_extra = {"example": {"text": "مرحباً بكم في منصة دبلجة عربية", "speed": 1.0}}


class TTSResponse(BaseModel):
    job_id: str
    status: str
    audio_url: Optional[str] = None
    bytes_size: Optional[int] = None
    output_key: Optional[str] = None


class TTSJobResponse(BaseModel):
    job_id: str
    status: str
    output_data: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


# ── DB helpers ────────────────────────────────────────────────────────────────


_ENGINE, _SessionLocal = make_engine(settings.DATABASE_URL)


def _make_db():
    return _ENGINE, _SessionLocal


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── endpoints ────────────────────────────────────────────────────────────────


@router.post("/synthesize", response_model=TTSResponse)
def synthesize(req: TTSRequest):
    """Synthesize TTS audio synchronously. Uploads result to MinIO, returns URL."""
    job_id = req.job_id or str(uuid.uuid4())
    minio_key = f"tts/standalone/{job_id}.wav"

    # Resolve a valid user_id for the jobs table FK
    user_id_val = None
    _, SessionLocal = _make_db()
    with SessionLocal() as db:
        row = db.execute(text("SELECT user_id FROM users ORDER BY user_id LIMIT 1")).fetchone()
        if row:
            user_id_val = row[0]
        db.execute(
            text("""
                INSERT INTO jobs (id, user_id, job_type, status, progress, input_data, created_at, updated_at)
                VALUES (:id, :uid, 'TTS_SYNTHESIZE', 'QUEUED', 0.0, CAST(:input AS jsonb), :now, :now)
            """),
            {"id": job_id, "uid": user_id_val, "input": json.dumps({"text": req.text}), "now": _utcnow()},
        )
        db.commit()

    try:
        audio_bytes = _tts_model.synthesize(
            text=req.text,
            ref_audio_path=req.ref_audio_path,
            ref_text=req.ref_text,
            speed=req.speed,
            cfg_strength=req.cfg_strength,
            nfe_step=req.nfe_step,
            sway_sampling_coef=req.sway_sampling_coef,
            target_rms=req.target_rms,
            seed=req.seed,
        )

        upload_wav(audio_bytes, minio_key)

        with SessionLocal() as db:
            db.execute(
                text("""
                    UPDATE jobs
                       SET status='COMPLETED', output_data=CAST(:output AS jsonb),
                           progress=100.0, completed_at=:now, updated_at=:now
                     WHERE id=:jid
                """),
                {
                    "output": json.dumps({"output_key": minio_key, "bytes_size": len(audio_bytes)}),
                    "now": _utcnow(),
                    "jid": job_id,
                },
            )
            db.commit()

        logger.info("[TTS] standalone synthesis done | job=%s | bytes=%d", job_id, len(audio_bytes))
        return TTSResponse(
            job_id=job_id,
            status="completed",
            audio_url=f"s3://{settings.S3_MEDIA_BUCKET}/{minio_key}",
            bytes_size=len(audio_bytes),
            output_key=minio_key,
        )

    except Exception as exc:
        logger.exception("[TTS] standalone synthesis failed | job=%s: %s", job_id, exc)
        try:
            with SessionLocal() as db:
                db.execute(
                    text("""
                        UPDATE jobs
                           SET status='FAILED', error_message=:error,
                               completed_at=:now, updated_at=:now
                         WHERE id=:jid
                    """),
                    {"error": str(exc), "now": _utcnow(), "jid": job_id},
                )
                db.commit()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {str(exc)}")


@router.get("/status/{job_id}", response_model=TTSJobResponse)
def get_status(job_id: str):
    """Get TTS job status from database."""
    _, SessionLocal = _make_db()
    with SessionLocal() as db:
        row = db.execute(
            text("SELECT id, status, output_data, error_message, created_at, completed_at FROM jobs WHERE id=:jid"),
            {"jid": job_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return TTSJobResponse(
        job_id=row[0],
        status=row[1],
        output_data=row[2] or {},
        error_message=row[3],
        created_at=row[4].isoformat() if row[4] else None,
        completed_at=row[5].isoformat() if row[5] else None,
    )


@router.get("/jobs/{job_id}", response_model=TTSJobResponse)
def get_job(job_id: str):
    """Get TTS job detail from database."""
    return get_status(job_id)


@router.get("/tts-health", include_in_schema=False)
def tts_health():
    return {
        "status": "healthy",
        "service": "tts",
        "model_loaded": _tts_model._model is not None,
        "device": _tts_model.device,
    }
