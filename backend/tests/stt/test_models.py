"""
Unit tests for STT models.
Location: tests/stt/test_models.py
"""

import pytest
import os
from unittest.mock import patch, MagicMock
from app.stt.models import clean_text, WhisperModelManager


class TestCleanText:
    """Test clean_text utility function."""

    def test_clean_text_single_space(self):
        """Test clean_text with single space."""
        result = clean_text("Hello world")
        assert result == "Hello world"

    def test_clean_text_multiple_spaces(self):
        """Test clean_text removes multiple spaces."""
        result = clean_text("Hello  world")
        assert result == "Hello world"

    def test_clean_text_leading_trailing_spaces(self):
        """Test clean_text removes leading/trailing spaces."""
        result = clean_text("  Hello world  ")
        assert result == "Hello world"

    def test_clean_text_newlines(self):
        """Test clean_text handles newlines."""
        result = clean_text("Hello\nworld")
        assert result == "Hello world"

    def test_clean_text_tabs(self):
        """Test clean_text handles tabs."""
        result = clean_text("Hello\tworld")
        assert result == "Hello world"

    def test_clean_text_empty_string(self):
        """Test clean_text with empty string."""
        result = clean_text("")
        assert result == ""


class TestWhisperModelManager:
    """Test WhisperModelManager class."""

    @patch("app.stt.models.WhisperModel")
    def test_init_default_model_size(self, mock_whisper):
        """Test initialization with default model size."""
        os.environ["STT_MODEL_SIZE"] = "small"

        manager = WhisperModelManager()

        assert manager.model_size == "small"
        assert manager.device in ["cuda", "cpu", "auto"]
        assert manager.compute_type in ["float32", "float16", "int8", "auto"]

    @patch("app.stt.models.WhisperModel")
    def test_init_custom_model_size(self, mock_whisper):
        """Test initialization with custom model size."""
        manager = WhisperModelManager(model_size="medium")

        assert manager.model_size == "medium"

    @patch("app.stt.models.WhisperModel")
    def test_init_device_cpu(self, mock_whisper):
        """Test initialization with CPU device."""
        manager = WhisperModelManager(device="cpu")

        assert manager.device == "cpu"

    @patch("app.stt.models.WhisperModel")
    def test_metrics_initialization(self, mock_whisper):
        """Test metrics are initialized."""
        manager = WhisperModelManager()

        assert manager.metrics["total_requests"] == 0
        assert manager.metrics["successful_transcriptions"] == 0
        assert manager.metrics["failed_transcriptions"] == 0
        assert manager.metrics["avg_processing_time"] == 0

    @patch("app.stt.models.WhisperModel")
    def test_validate_audio_file_exists(self, mock_whisper, test_audio_file):
        """Test audio file validation - file exists."""
        manager = WhisperModelManager()

        # Should not raise exception
        manager._validate_audio_file(str(test_audio_file))

    @patch("app.stt.models.WhisperModel")
    def test_validate_audio_file_not_found(self, mock_whisper):
        """Test audio file validation - file not found."""
        manager = WhisperModelManager()

        with pytest.raises(FileNotFoundError):
            manager._validate_audio_file("/nonexistent/file.mp3")

    @patch("app.stt.models.WhisperModel")
    def test_validate_audio_file_invalid_extension(self, mock_whisper, tmp_path):
        """Test audio file validation - invalid extension."""
        manager = WhisperModelManager()

        invalid_file = tmp_path / "test.txt"
        invalid_file.write_text("test content")

        with pytest.raises(ValueError, match="Unsupported audio format"):
            manager._validate_audio_file(str(invalid_file))

    @patch("app.stt.models.WhisperModel")
    def test_validate_audio_file_too_large(self, mock_whisper, tmp_path):
        """Test audio file validation - file too large."""
        manager = WhisperModelManager()

        large_file = tmp_path / "test.mp3"
        large_file.write_bytes(b"x" * (2 * 1024 * 1024))  # 2 MB

        # Patch the settings object directly since env vars won't affect already-loaded config
        with patch("app.stt.models.settings") as mock_settings:
            mock_settings.STT_MAX_FILE_SIZE_GB = 0.001  # ~1 MB limit
            mock_settings.STT_GPU_MEMORY_THRESHOLD = 0.9

            with pytest.raises(ValueError, match="File too large"):
                manager._validate_audio_file(str(large_file))

    @patch("app.stt.models.WhisperModel")
    def test_check_gpu_memory_cpu(self, mock_whisper):
        """Test GPU memory check on CPU."""
        manager = WhisperModelManager(device="cpu")

        # Should always return True on CPU
        assert manager._check_gpu_memory() is True

    @patch("app.stt.models.WhisperModel")
    def test_get_metrics(self, mock_whisper):
        """Test get_metrics returns proper structure."""
        manager = WhisperModelManager()
        metrics = manager.get_metrics()

        assert "total_requests" in metrics
        assert "successful_transcriptions" in metrics
        assert "failed_transcriptions" in metrics
        assert "device" in metrics
        assert "model_size" in metrics
        assert "is_transcribing" in metrics

    @patch("app.stt.models.WhisperModel")
    def test_cleanup(self, mock_whisper):
        """Test cleanup method."""
        manager = WhisperModelManager()

        # Should not raise exception
        manager.cleanup()

    @patch("app.stt.models.WhisperModel")
    def test_concurrent_transcription_prevention(self, mock_whisper):
        """Test that concurrent transcriptions are prevented."""
        manager = WhisperModelManager()
        manager._is_transcribing = True

        # Bypass file validation and GPU check so we reach the concurrency check
        with patch.object(manager, "_validate_audio_file"):
            with patch.object(manager, "_check_gpu_memory", return_value=True):
                with pytest.raises(RuntimeError, match="already in progress"):
                    manager.transcribe("dummy.mp3")
