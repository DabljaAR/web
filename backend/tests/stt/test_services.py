"""
Unit tests for STT services.
Location: tests/stt/test_services.py
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from fastapi import UploadFile
from pathlib import Path
from app.stt.services import TranscriptionService
from io import BytesIO


class TestTranscriptionService:
    """Test TranscriptionService class."""

    @pytest.fixture
    def mock_model_manager(self):
        """Create mock model manager."""
        mock = MagicMock()
        mock.transcribe.return_value = {
            "transcript": "Hello world",
            "segments": [{"start": 0.0, "end": 2.5, "text": "Hello world"}],
            "metadata": {
                "language": "en",
                "duration": 2.5,
                "model_size": "small",
                "device": "cpu",
                "processing_time": 1.0,
                "segment_count": 1,
            }
        }
        mock.get_metrics.return_value = {
            "total_requests": 10,
            "successful_transcriptions": 9,
            "failed_transcriptions": 1,
            "avg_processing_time": 5.0,
            "device": "cpu",
            "model_size": "small",
            "is_transcribing": False,
        }
        return mock

    def test_service_initialization(self, mock_model_manager):
        """Test service initialization."""
        service = TranscriptionService(mock_model_manager)

        assert service.model_manager == mock_model_manager

    def test_ensure_upload_dir(self):
        """Test upload directory is created."""
        service = TranscriptionService(MagicMock())

        # Should not raise exception
        service._ensure_upload_dir()

    @pytest.mark.asyncio
    async def test_transcribe_file(self, mock_model_manager):
        """Test transcribe_file method."""
        service = TranscriptionService(mock_model_manager)

        # Use plain MagicMock (no spec) so .file attribute is not blocked
        mock_file = MagicMock()
        mock_file.filename = "test.mp3"
        mock_file.read = AsyncMock(return_value=b"fake audio data")

        with patch.object(service, "_save_upload", return_value=Path("/tmp/test.mp3")):
            with patch.object(
                service.model_manager,
                "transcribe",
                return_value=mock_model_manager.transcribe.return_value
            ):
                result = await service.transcribe_file(mock_file, language="en")

        assert result.transcript == "Hello world"
        assert len(result.segments) > 0
        assert result.metadata.language == "en"

    @pytest.mark.asyncio
    async def test_submit_async_transcription(self, mock_model_manager):
        """Test submit_async_transcription method."""
        service = TranscriptionService(mock_model_manager)

        mock_file = MagicMock()
        mock_file.filename = "test.mp3"
        mock_file.read = AsyncMock(return_value=b"fake audio data")

        with patch.object(service, "_save_upload", return_value=Path("/tmp/test.mp3")):
            result = await service.submit_async_transcription(mock_file, language="en")

        assert "task_id" in result
        assert result["status"] == "queued"
        assert "message" in result

    def test_get_job_status_success(self, mock_model_manager):
        """Test get_job_status for successful job."""
        service = TranscriptionService(mock_model_manager)

        from app.stt.services import JOB_STORAGE
        task_id = "test-task-123"
        JOB_STORAGE[task_id] = {
            "status": "success",
            "filename": "test.mp3",
            "file_path": "/tmp/test.mp3",
            "language": "en",
            "result": {"transcript": "test"},
            "error": None
        }

        result = service.get_job_status(task_id)

        assert result["task_id"] == task_id
        assert result["status"] == "success"
        assert result["result"]["transcript"] == "test"

    def test_get_job_status_not_found(self, mock_model_manager):
        """Test get_job_status for non-existent job."""
        service = TranscriptionService(mock_model_manager)

        with pytest.raises(KeyError):
            service.get_job_status("nonexistent-task-id")

    def test_get_metrics(self, mock_model_manager):
        """Test get_metrics method."""
        service = TranscriptionService(mock_model_manager)

        metrics = service.get_metrics()

        assert "total_requests" in metrics
        assert "success_rate" in metrics
        assert 0 <= metrics["success_rate"] <= 100

    def test_get_health(self, mock_model_manager):
        """Test get_health method."""
        service = TranscriptionService(mock_model_manager)

        health = service.get_health()

        assert health["status"] == "healthy"
        assert health["model_loaded"] is True
        assert "device" in health
        assert "version" in health

    def test_cleanup(self, mock_model_manager):
        """Test cleanup method."""
        service = TranscriptionService(mock_model_manager)

        # Should not raise exception
        service.cleanup()

    def test_save_upload(self, tmp_path):
        """Test _save_upload method."""
        service = TranscriptionService(MagicMock())

        mock_file = MagicMock()
        mock_file.filename = "test.mp3"
        mock_file.file = BytesIO(b"fake audio data")

        with patch("app.stt.services.UPLOAD_DIR", tmp_path):
            path = service._save_upload(mock_file)

        assert path.exists()
        assert path.name.endswith("test.mp3")


class TestAsyncTranscriptionWorker:
    """Test AsyncTranscriptionWorker class."""

    def test_worker_initialization(self):
        """Test worker initialization."""
        from app.stt.services import AsyncTranscriptionWorker

        service = TranscriptionService(MagicMock())
        worker = AsyncTranscriptionWorker(service)

        assert worker.service == service

    def test_process_job(self):
        """Test process_job method."""
        from app.stt.services import AsyncTranscriptionWorker, JOB_STORAGE

        service = TranscriptionService(MagicMock())
        worker = AsyncTranscriptionWorker(service)

        task_id = "test-task-456"
        JOB_STORAGE[task_id] = {
            "status": "queued",
            "filename": "test.mp3",
            "file_path": "/tmp/test.mp3",
            "language": "en",
            "result": None,
            "error": None
        }

        with patch.object(service, "process_async_transcription"):
            worker.process_job(task_id)
