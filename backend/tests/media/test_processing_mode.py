"""Unit tests for processing mode resolution in media service."""
from unittest.mock import patch


def test_resolve_processing_mode_tts_focused_for_eligible_outputs():
    """Eligible output types should honor tts_focused mode."""
    from app.shared.processing_mode import resolve_processing_mode

    with patch("app.shared.processing_mode.settings.PIPELINE_SEGMENTS_MODE", "tts_focused"):
        assert resolve_processing_mode("fullDubbing") == "tts_focused"
        assert resolve_processing_mode("captionsOnly") == "tts_focused"


def test_resolve_processing_mode_non_eligible_forces_stt_focused():
    """Non-eligible output types should always preserve STT segmentation."""
    from app.shared.processing_mode import resolve_processing_mode

    with patch("app.shared.processing_mode.settings.PIPELINE_SEGMENTS_MODE", "single"):
        assert resolve_processing_mode("uploadOnly") == "stt_focused"


def test_resolve_processing_mode_invalid_falls_back_to_single():
    """Invalid mode should fallback to single for eligible output types."""
    from app.shared.processing_mode import resolve_processing_mode

    with patch("app.shared.processing_mode.settings.PIPELINE_SEGMENTS_MODE", "invalid_mode"):
        assert resolve_processing_mode("fullDubbing") == "single"
