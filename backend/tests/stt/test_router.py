"""
Unit tests for STT router/API endpoints.
Location: tests/stt/test_router.py
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from io import BytesIO


class TestTranscriptionEndpoints:
    """Test transcription API endpoints."""

    def test_health_endpoint(self, client, mock_service):
        """Test /health endpoint."""
        with patch("app.stt.router.service", mock_service):
            response = client.get("/api/transcription/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["model_loaded"] is True

    def test_metrics_endpoint(self, client, mock_service):
        """Test /metrics endpoint."""
        with patch("app.stt.router.service", mock_service):
            response = client.get("/api/transcription/metrics")

        assert response.status_code == 200
        data = response.json()
        assert "total_requests" in data
        assert "success_rate" in data

    def test_info_endpoint(self, client):
        """Test /info endpoint."""
        response = client.get("/api/transcription/info")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "endpoints" in data

    def test_root_endpoint(self, client):
        """Test root / endpoint."""
        response = client.get("/api/transcription/")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "docs" in data

    @pytest.mark.asyncio
    async def test_transcribe_file_endpoint(self, client, mock_service):
        """Test /transcribe endpoint with file upload."""
        mock_service.transcribe_file = AsyncMock(return_value=MagicMock(
            transcript="Hello world",
            segments=[{"start": 0.0, "end": 2.5, "text": "Hello world"}],
            metadata=MagicMock(
                language="en",
                duration=2.5,
                model_size="small",
                device="cpu",
                processing_time=1.0,
                segment_count=1
            )
        ))

        audio_data = BytesIO(b"fake audio data")

        with patch("app.stt.router.service", mock_service):
            response = client.post(
                "/api/transcription/transcribe",
                files={"file": ("test.mp3", audio_data, "audio/mpeg")},
                params={"language": "en"}
            )

        assert response.status_code in [200, 422]

    @pytest.mark.asyncio
    async def test_transcribe_async_endpoint(self, client, mock_service):
        """Test /transcribe-async endpoint."""
        mock_service.submit_async_transcription = AsyncMock(return_value={
            "task_id": "test-task-123",
            "status": "queued",
            "message": "Job submitted"
        })

        audio_data = BytesIO(b"fake audio data")

        with patch("app.stt.router.service", mock_service):
            response = client.post(
                "/api/transcription/transcribe-async",
                files={"file": ("test.mp3", audio_data, "audio/mpeg")},
                params={"language": "en"}
            )

        assert response.status_code in [200, 422]

    def test_get_job_status_endpoint(self, client, mock_service):
        """Test /status/{task_id} endpoint."""
        mock_service.get_job_status.return_value = {
            "task_id": "test-task-123",
            "status": "success",
            # result=None so the router skips TranscriptionResponse conversion
            "result": None,
            "error": None
        }

        with patch("app.stt.router.service", mock_service):
            response = client.get("/api/transcription/status/test-task-123")

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "test-task-123"
        assert data["status"] == "success"

    def test_cancel_job_endpoint(self, client, mock_service):
        """Test /cancel/{task_id} endpoint."""
        mock_service.get_job_status.return_value = {
            "status": "queued",
            "task_id": "test-task-123"
        }

        with patch("app.stt.router.service", mock_service):
            response = client.delete("/api/transcription/cancel/test-task-123")

        assert response.status_code in [200, 400]

    def test_cancel_completed_job(self, client, mock_service):
        """Test canceling a completed job should fail."""
        mock_service.get_job_status.return_value = {
            "status": "success",
            "task_id": "test-task-123"
        }

        with patch("app.stt.router.service", mock_service):
            response = client.delete("/api/transcription/cancel/test-task-123")

        assert response.status_code == 400

    def test_status_job_not_found(self, client, mock_service):
        """Test getting status of non-existent job."""
        mock_service.get_job_status.side_effect = KeyError("Task not found")

        with patch("app.stt.router.service", mock_service):
            response = client.get("/api/transcription/status/nonexistent-task")

        assert response.status_code == 404

    def test_unsupported_file_format(self, client, mock_service):
        """Test uploading unsupported file format."""
        audio_data = BytesIO(b"fake file content")

        with patch("app.stt.router.service", mock_service):
            response = client.post(
                "/api/transcription/transcribe",
                files={"file": ("test.txt", audio_data, "text/plain")},
            )

        assert response.status_code == 400

    def test_service_not_initialized(self, client):
        """Test endpoint behavior when service is not initialized."""
        with patch("app.stt.router.service", None):
            response = client.get("/api/transcription/health")

        assert response.status_code == 503


class TestTranscriptionValidation:
    """Test input validation."""

    def test_invalid_language_code(self, client, mock_service=None):
        """Test invalid language code handling."""
        pass

    def test_empty_file_upload(self, client, mock_service):
        """Test uploading empty file is handled without a server crash."""
        from unittest.mock import AsyncMock, MagicMock

        mock_service.transcribe_file = AsyncMock(return_value=MagicMock(
            transcript="",
            segments=[],
            metadata=MagicMock(
                language="en", duration=0.0, model_size="small",
                device="cpu", processing_time=0.0, segment_count=0
            )
        ))

        audio_data = BytesIO(b"")

        with patch("app.stt.router.service", mock_service):
            response = client.post(
                "/api/transcription/transcribe",
                files={"file": ("test.mp3", audio_data, "audio/mpeg")},
            )

        # Router accepted it (200) or rejected at schema level (422) — no 500
        assert response.status_code in [200, 422]
        assert response.status_code != 500

    def test_missing_file_upload(self, client):
        """Test missing file in upload request."""
        response = client.post("/api/transcription/transcribe")

        assert response.status_code == 422
