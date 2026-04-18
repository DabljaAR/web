"""Pipeline processing mode resolution helpers."""

from app.config import (
    PIPELINE_SEGMENTS_MODE_ALLOWED,
    PIPELINE_SEGMENTS_MODE_DEFAULT,
    settings,
)

CHUNK_ELIGIBLE_OUTPUT_TYPES = {
    "captionsOnly",
    "captionsAndTranslation",
    "translationAndTTS",
    "fullDubbing",
}


def resolve_processing_mode(output_type: str) -> str:
    """Resolve runtime processing mode from config and output type.

    For non-eligible output types, force `stt_focused` (preserve STT segmentation).
    """
    requested_mode = str(settings.PIPELINE_SEGMENTS_MODE or "").strip().lower()
    if requested_mode not in PIPELINE_SEGMENTS_MODE_ALLOWED:
        requested_mode = PIPELINE_SEGMENTS_MODE_DEFAULT

    if output_type not in CHUNK_ELIGIBLE_OUTPUT_TYPES:
        return "stt_focused"

    return requested_mode
