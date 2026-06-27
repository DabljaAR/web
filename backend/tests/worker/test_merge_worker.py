"""Unit tests for the Merge worker handler."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.merge_worker import create_worker, handle_merge


class TestMergeWorkerHandler:
    def test_create_worker_configures_handler(self):
        worker = create_worker("amqp://localhost/", concurrency=2)
        assert worker._worker_name == "merge"
        assert "job.start.merge" in worker._handlers

    async def test_handler_merges_segments(self):
        tts_output = {
            "segments": [
                {
                    "segment_id": 0,
                    "start": 0.0,
                    "end": 2.5,
                    "translated_text": "مرحبا",
                    "tts_key": "tts/job-001/segment_0.wav",
                },
                {
                    "segment_id": 1,
                    "start": 2.5,
                    "end": 5.0,
                    "translated_text": "عالم",
                    "tts_key": "tts/job-001/segment_1.wav",
                },
            ],
        }
        tts_job = {
            "id": "tts-child-001",
            "video_id": "vid-001",
            "user_id": 42,
            "input_data": {},
            "output_data": tts_output,
        }

        mock_merge_response = MagicMock()
        mock_merge_response.output_key = "dubbed/vid-001/final.mp4"
        mock_merge_response.output_url = "https://minio/dubbed/vid-001/final.mp4"
        mock_merge_response.metadata = {
            "combined_audio_key": "tts/job-001/combined.wav",
        }

        mock_engine = MagicMock()
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("app.worker.merge_worker.load_job", return_value=tts_job), \
             patch("app.worker.merge_worker.create_child_job", return_value="merge-child-001"), \
             patch("app.worker.merge_worker.update_job_output") as mock_update, \
             patch("app.worker.merge_worker._get_video_media_type", return_value="video"), \
             patch("app.worker.merge_worker._get_original_media_key", return_value="videos/42/original.mp4"), \
             patch("app.worker.merge_worker.DubbingMergeService") as mock_merge_svc_cls, \
             patch("app.worker.merge_worker._make_engine",
                   return_value=(mock_engine, MagicMock(return_value=mock_session))):
            mock_merge_svc = AsyncMock()
            mock_merge_svc.merge_segments.return_value = mock_merge_response
            mock_merge_svc_cls.return_value = mock_merge_svc

            result = await handle_merge("tts-child-001")

        assert result["_result_job_id"] == "merge-child-001"
        assert result["status"] == "completed"
        assert result["output_key"] == "dubbed/vid-001/final.mp4"
        assert result["output_url"] == "https://minio/dubbed/vid-001/final.mp4"
        assert result["metadata"]["segments_merged"] == 2
        mock_update.assert_called()

    async def test_handler_handles_no_valid_segments(self):
        tts_output = {
            "segments": [
                {
                    "segment_id": 0,
                    "tts_key": None,
                    "tts_error": "Synthesis failed",
                },
            ],
        }
        tts_job = {
            "id": "tts-child-001",
            "video_id": "vid-001",
            "user_id": 42,
            "input_data": {},
            "output_data": tts_output,
        }

        with patch("app.worker.merge_worker.load_job", return_value=tts_job), \
             patch("app.worker.merge_worker.create_child_job", return_value="merge-child-001"), \
             patch("app.worker.merge_worker.update_job_output"):
            result = await handle_merge("tts-child-001")

        assert result["status"] == "failed"
        assert "No valid TTS segments" in result.get("error", "")

    async def test_handler_raises_on_missing_video_id(self):
        tts_job = {
            "id": "tts-child-001",
            "video_id": None,
            "user_id": 42,
            "input_data": {},
            "output_data": {"segments": [{"tts_key": "some-key"}]},
        }

        with patch("app.worker.merge_worker.load_job", return_value=tts_job):
            with pytest.raises(ValueError, match="No video_id"):
                await handle_merge("tts-child-001")

    async def test_handler_raises_on_missing_job(self):
        with patch("app.worker.merge_worker.load_job", return_value=None):
            with pytest.raises(ValueError, match="not found"):
                await handle_merge("nonexistent")

    async def test_handler_updates_video_record(self):
        tts_output = {
            "segments": [
                {
                    "segment_id": 0,
                    "start": 0.0,
                    "end": 2.5,
                    "translated_text": "مرحبا",
                    "tts_key": "tts/job-001/segment_0.wav",
                },
            ],
        }
        tts_job = {
            "id": "tts-child-001",
            "video_id": "vid-001",
            "user_id": 42,
            "input_data": {},
            "output_data": tts_output,
        }

        mock_merge_response = MagicMock()
        mock_merge_response.output_key = "dubbed/vid-001/final.mp4"
        mock_merge_response.output_url = "https://minio/dubbed/vid-001/final.mp4"
        mock_merge_response.metadata = {}

        mock_engine = MagicMock()
        mock_session = MagicMock()
        mock_video_row = MagicMock()
        mock_session.get.return_value = mock_video_row
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("app.worker.merge_worker.load_job", return_value=tts_job), \
             patch("app.worker.merge_worker.create_child_job", return_value="merge-child-001"), \
             patch("app.worker.merge_worker.update_job_output"), \
             patch("app.worker.merge_worker._get_video_media_type", return_value="video"), \
             patch("app.worker.merge_worker._get_original_media_key", return_value="videos/42/original.mp4"), \
             patch("app.worker.merge_worker.DubbingMergeService") as mock_merge_svc_cls, \
             patch("app.worker.merge_worker._make_engine",
                   return_value=(mock_engine, MagicMock(return_value=mock_session))):
            mock_merge_svc = AsyncMock()
            mock_merge_svc.merge_segments.return_value = mock_merge_response
            mock_merge_svc_cls.return_value = mock_merge_svc

            await handle_merge("tts-child-001")

        assert mock_video_row.dubbed_video_path == "dubbed/vid-001/final.mp4"
        assert mock_video_row.dubbing_metadata["merge_job_id"] == "merge-child-001"
        mock_session.commit.assert_called()
