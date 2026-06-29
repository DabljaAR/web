import io
import logging
from pathlib import Path
from typing import List, Optional

import soundfile as sf
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.model import OmniVoiceManager
from app.storage import upload_audio

logger = logging.getLogger(__name__)
router = APIRouter()


class SynthesizeRequest(BaseModel):
    text: str
    ref_audio: Optional[str] = None
    ref_text: Optional[str] = None
    instruct: Optional[str] = None
    num_step: Optional[int] = None
    guidance_scale: Optional[float] = None
    speed: Optional[float] = None


class SynthesizeResponse(BaseModel):
    audio_url: str
    duration_seconds: float
    sample_rate: int = 24000
    key: str


class BatchSegment(BaseModel):
    id: int
    text: str
    start: Optional[float] = None
    end: Optional[float] = None


class BatchSynthesizeRequest(BaseModel):
    segments: List[BatchSegment]
    ref_audio: Optional[str] = None
    ref_text: Optional[str] = None
    instruct: Optional[str] = None


class BatchSegmentResult(BaseModel):
    id: int
    audio_url: Optional[str] = None
    key: Optional[str] = None
    error: Optional[str] = None


class BatchSynthesizeResponse(BaseModel):
    segments: List[BatchSegmentResult]


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize(req: SynthesizeRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text must not be empty")

    try:
        audio_list = await run_in_threadpool(
            _synthesize_internal,
            text=req.text,
            ref_audio=req.ref_audio,
            ref_text=req.ref_text,
            instruct=req.instruct,
        )
    except Exception as exc:
        logger.exception("TTS synthesis failed: %s", exc)
        raise HTTPException(status_code=500, detail="TTS synthesis failed")

    if not audio_list or len(audio_list) == 0:
        raise HTTPException(status_code=500, detail="TTS produced no audio output")

    audio = audio_list[0]
    sample_rate = 24000

    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format="WAV")
    wav_bytes = buf.getvalue()

    duration = len(audio) / sample_rate
    key = f"tts/sync/{Path(req.text[:32]).stem}_{id(req)}.wav"
    url = upload_audio(wav_bytes, key)

    return SynthesizeResponse(
        audio_url=url,
        duration_seconds=round(duration, 2),
        sample_rate=sample_rate,
        key=key,
    )


@router.post("/synthesize/batch", response_model=BatchSynthesizeResponse)
async def synthesize_batch(req: BatchSynthesizeRequest):
    if not req.segments:
        raise HTTPException(status_code=400, detail="segments must not be empty")

    results = []
    for seg in req.segments:
        text = seg.text.strip()
        if not text:
            results.append(BatchSegmentResult(id=seg.id, error="empty text"))
            continue

        try:
            audio_list = await run_in_threadpool(
                _synthesize_internal,
                text=text,
                ref_audio=req.ref_audio,
                ref_text=req.ref_text,
                instruct=req.instruct,
            )
            if not audio_list:
                results.append(BatchSegmentResult(id=seg.id, error="no audio output"))
                continue

            audio = audio_list[0]
            buf = io.BytesIO()
            sf.write(buf, audio, 24000, format="WAV")
            wav_bytes = buf.getvalue()

            key = f"tts/batch/segment_{seg.id}.wav"
            url = upload_audio(wav_bytes, key)
            results.append(BatchSegmentResult(id=seg.id, audio_url=url, key=key))
        except Exception as exc:
            logger.exception("Batch segment %d synthesis failed", seg.id)
            results.append(BatchSegmentResult(id=seg.id, error=str(exc)))

    return BatchSynthesizeResponse(segments=results)


@router.get("/health/model")
def health_model():
    return {
        "model_loaded": OmniVoiceManager.is_loaded(),
        "device": OmniVoiceManager.device(),
        "model_name": OmniVoiceManager.model_name(),
    }


def _synthesize_internal(
    text: str,
    ref_audio: Optional[str] = None,
    ref_text: Optional[str] = None,
    instruct: Optional[str] = None,
):
    return OmniVoiceManager.synthesize(
        text=text,
        ref_audio=ref_audio,
        ref_text=ref_text,
        instruct=instruct,
    )
