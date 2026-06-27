"""Unit tests for the STT worker handler."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.stt_worker import handle_stt, create_worker


class TestSttWorkerHandler:
    def test_create_worker_configures_handler(self):
        worker = create_worker("amqp://localhost/", concurrency=1)
        assert worker._worker_name == "stt"
        assert "job.start.stt" in worker._handlers

    async def test_handler_pipeline_flow(self):
        """Verify end-to-end flow: load job → create child → transcribe → return."""
        mock_pipeline_job = {
            "id": "pipeline-001",
            "video_id": "vid-001",
            "user_id": 42,
            "input_data": {
                "source_lang": "en",
                "target_lang": "arb_Arab",
                "processing_mode": "single",
            },
            "output_data": {},
        }

        mock_segments = [
            MagicMock(start=0.0, end=2.5, text="Hello world"),
            MagicMock(start=2.5, end=5.0, text="This is a test"),
        ]
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.duration = 5.0

        mock_whisper = MagicMock()
        mock_whisper.model.transcribe.return_value = (iter(mock_segments), mock_info)

        with patch("app.worker.stt_worker.load_job", return_value=mock_pipeline_job), \
             patch("app.worker.stt_worker.create_child_job", return_value="stt-child-001") as mock_create_child_job, \
             patch("app.worker.stt_worker.update_job_output") as mock_update, \
             patch("app.worker.stt_worker.get_video_file_key", return_value="audio/42/test.mp3"), \
             patch("app.worker.stt_worker.get_storage_service") as mock_get_storage, \
             patch("app.worker.stt_worker.WhisperModelManager", return_value=mock_whisper), \
             patch("asyncio.new_event_loop") as mock_loop_factory:
            mock_storage = MagicMock()
            mock_storage.download = AsyncMock(return_value=True)
            mock_get_storage.return_value = mock_storage
            mock_loop = MagicMock()
            mock_loop.run_until_complete = MagicMock(return_value=True)
            mock_loop_factory.return_value = mock_loop

            result = await handle_stt("pipeline-001")

        # Verify child job was created with the pipeline id
        mock_create_child_job.assert_called_once()

        # Verify output
        assert result["_result_job_id"] == "stt-child-001"
        assert result["status"] == "completed"
        assert result["video_id"] == "vid-001"
        assert len(result["segments"]) == 2
        assert result["segments"][0]["text"] == "Hello world"
        assert result["transcript"] == "Hello world This is a test"

        # Verify DB was updated
        mock_update.assert_called()

    async def test_handler_raises_on_missing_job(self):
        with patch("app.worker.stt_worker.load_job", return_value=None):
            with pytest.raises(ValueError, match="not found"):
                await handle_stt("nonexistent")

    async def test_handler_raises_on_missing_video_id(self):
        with patch("app.worker.stt_worker.load_job", return_value={
            "id": "pipeline-001",
            "video_id": None,
            "user_id": 42,
            "input_data": {},
            "output_data": {},
        }):
            with pytest.raises(ValueError, match="no video_id"):
                await handle_stt("pipeline-001")

    async def test_handler_raises_on_transcription_failure(self):
        mock_pipeline_job = {
            "id": "pipeline-001",
            "video_id": "vid-001",
            "user_id": 42,
            "input_data": {"source_lang": "en"},
            "output_data": {},
        }

        mock_whisper = MagicMock()
        mock_whisper.model.transcribe.side_effect = RuntimeError("Whisper crashed")

        with patch("app.worker.stt_worker.load_job", return_value=mock_pipeline_job), \
             patch("app.worker.stt_worker.create_child_job", return_value="stt-child-001"), \
             patch("app.worker.stt_worker.update_job_output"), \
             patch("app.worker.stt_worker.get_video_file_key", return_value="audio/42/test.mp3"), \
             patch("app.worker.stt_worker.get_storage_service"), \
             patch("app.worker.stt_worker.WhisperModelManager", return_value=mock_whisper), \
             patch("asyncio.new_event_loop"):
            with pytest.raises(RuntimeError, match="Whisper crashed"):
                await handle_stt("pipeline-001")
