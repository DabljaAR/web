"""Unit tests for processing mode resolution in media service."""
from unittest.mock import patch


def test_resolve_processing_mode_single_chunk_enabled():
    """Eligible output types should use single_chunk when the flag is enabled."""
    from app.media.service import _resolve_processing_mode

    with patch("app.media.service.settings.PIPELINE_USE_SINGLE_CHUNK", True):
        assert _resolve_processing_mode("fullDubbing") == "single_chunk"
        assert _resolve_processing_mode("captionsOnly") == "single_chunk"


def test_resolve_processing_mode_upload_only_stays_segmented():
    """uploadOnly should remain segmented even when the flag is enabled."""
    from app.media.service import _resolve_processing_mode

    with patch("app.media.service.settings.PIPELINE_USE_SINGLE_CHUNK", True):
        assert _resolve_processing_mode("uploadOnly") == "segmented"


def test_resolve_processing_mode_flag_disabled():
    """When the flag is disabled, all output types stay segmented."""
    from app.media.service import _resolve_processing_mode

    with patch("app.media.service.settings.PIPELINE_USE_SINGLE_CHUNK", False):
        assert _resolve_processing_mode("fullDubbing") == "segmented"
