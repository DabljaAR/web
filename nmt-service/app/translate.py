"""Sync translation endpoint for the NMT microservice.

POST /translate    — translate a text string immediately (for testing/direct use)
GET  /health/model — NLLB model load status
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.model import NLLBTranslatorWrapper

logger = logging.getLogger(__name__)

router = APIRouter()

_manager = NLLBTranslatorWrapper()


class TranslateRequest(BaseModel):
    text: str
    source_lang: Optional[str] = None
    target_lang: str = "arb_Arab"
    num_beams: int = 5
    english_ratio_threshold: float = 0.5


class TranslateResponse(BaseModel):
    translated_text: str
    source_lang: Optional[str]
    target_lang: str


@router.post("/translate", response_model=TranslateResponse, summary="Synchronous translation")
async def translate_sync(req: TranslateRequest):
    """Translate a single text string. Runs in a thread pool (non-blocking)."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text must not be empty")

    try:
        translated = await run_in_threadpool(
            _manager.translate_segment,
            req.text,
            src_lang=req.source_lang,
            tgt_lang=req.target_lang,
            num_beams=req.num_beams,
            english_ratio_threshold=req.english_ratio_threshold,
        )
    except Exception as exc:
        logger.exception("[NMT] Sync translation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Translation failed.")

    return TranslateResponse(
        translated_text=translated,
        source_lang=req.source_lang,
        target_lang=req.target_lang,
    )


@router.get("/health/model", summary="NLLB model load status")
def health_model():
    loaded = NLLBTranslatorWrapper._model is not None
    tok_loaded = NLLBTranslatorWrapper._tokenizer is not None
    return {
        "model_loaded": loaded,
        "tokenizer_loaded": tok_loaded,
        "device": _manager.device,
        "model_name": _manager.model_name if loaded else None,
    }
