"""Unit tests for the TTS worker handler."""
from unittest.mock import MagicMock, patch

import pytest

from app.worker.tts_worker import create_worker, handle_tts


class TestTtsWorkerHandler:
    def test_create_worker_configures_handler(self):
        worker = create_worker("amqp://localhost/", concurrency=1)
        assert worker._worker_name == "tts"
        assert "job.start.tts" in worker._handlers

    async def test_handler_synthesizes_segments(self):
        nmt_output = {
            "segments": [
                {
                    "segment_id": 0,
                    "start": 0.0,
                    "end": 2.5,
                    "original_text": "Hello",
                    "translated_text": "مرحبا",
                },
                {
                    "segment_id": 1,
                    "start": 2.5,
                    "end": 5.0,
                    "original_text": "World",
                    "translated_text": "عالم",
                },
            ],
        }
        nmt_job = {
            "id": "nmt-child-001",
            "video_id": "vid-001",
            "user_id": 42,
            "input_data": {"task_id": "task-001"},
            "output_data": nmt_output,
        }

        def fake_synthesize(text, ref_audio_path, job_id, upload_to_minio, minio_key):
            return {"minio_key": minio_key, "audio_url": f"https://minio/{minio_key}"}

        with patch("app.worker.tts_worker.load_job", return_value=nmt_job), \
             patch("app.worker.tts_worker.create_child_job", return_value="tts-child-001"), \
             patch("app.worker.tts_worker.update_job_output") as mock_update, \
             patch("app.worker.tts_worker.settings") as mock_settings, \
             patch("app.worker.tts_worker.synthesize_tts") as mock_synth:
            mock_synth.run.side_effect = fake_synthesize
            mock_settings.get_silma_reference_audio.return_value = "/path/to/ref.wav"

            result = await handle_tts("nmt-child-001")

        assert result["_result_job_id"] == "tts-child-001"
        assert result["status"] == "completed"
        assert len(result["segments"]) == 2
        assert result["segments"][0]["tts_key"] == "tts/tts-child-001/segment_0.wav"
        assert result["segments"][1]["tts_key"] == "tts/tts-child-001/segment_1.wav"
        assert result["segments"][0]["audio_url"] is not None
        mock_update.assert_called()

    async def test_handler_handles_empty_segments(self):
        nmt_job = {
            "id": "nmt-child-001",
            "video_id": "vid-001",
            "user_id": 42,
            "input_data": {},
            "output_data": {"segments": []},
        }

        with patch("app.worker.tts_worker.load_job", return_value=nmt_job), \
             patch("app.worker.tts_worker.create_child_job", return_value="tts-child-001"), \
             patch("app.worker.tts_worker.update_job_output"):
            result = await handle_tts("nmt-child-001")

        assert result["status"] == "completed"
        assert result["segments"] == []

    async def test_handler_skips_empty_text(self):
        nmt_output = {
            "segments": [
                {
                    "segment_id": 0,
                    "start": 0.0,
                    "end": 2.5,
                    "original_text": "",
                    "translated_text": "",
                },
                {
                    "segment_id": 1,
                    "start": 2.5,
                    "end": 5.0,
                    "original_text": "Hello",
                    "translated_text": "مرحبا",
                },
            ],
        }
        nmt_job = {
            "id": "nmt-child-001",
            "video_id": "vid-001",
            "user_id": 42,
            "input_data": {},
            "output_data": nmt_output,
        }

        def fake_synthesize(text, ref_audio_path, job_id, upload_to_minio, minio_key):
            return {"minio_key": minio_key, "audio_url": f"https://minio/{minio_key}"}

        with patch("app.worker.tts_worker.load_job", return_value=nmt_job), \
             patch("app.worker.tts_worker.create_child_job", return_value="tts-child-001"), \
             patch("app.worker.tts_worker.update_job_output"), \
             patch("app.worker.tts_worker.settings") as mock_settings, \
             patch("app.worker.tts_worker.synthesize_tts") as mock_synth:
            mock_synth.run.side_effect = fake_synthesize
            mock_settings.get_silma_reference_audio.return_value = "/path/to/ref.wav"

            result = await handle_tts("nmt-child-001")

        assert len(result["segments"]) == 2
        # First segment has no audio (empty text)
        assert result["segments"][0]["tts_key"] is None
        # Second segment has audio
        assert result["segments"][1]["tts_key"] is not None
        assert result["metadata"]["failed"] == 0

    async def test_handler_records_individual_segment_failures(self):
        nmt_output = {
            "segments": [
                {
                    "segment_id": 0,
                    "start": 0.0,
                    "end": 2.5,
                    "original_text": "Hello",
                    "translated_text": "مرحبا",
                },
            ],
        }
        nmt_job = {
            "id": "nmt-child-001",
            "video_id": "vid-001",
            "user_id": 42,
            "input_data": {},
            "output_data": nmt_output,
        }

        with patch("app.worker.tts_worker.load_job", return_value=nmt_job), \
             patch("app.worker.tts_worker.create_child_job", return_value="tts-child-001"), \
             patch("app.worker.tts_worker.update_job_output"), \
             patch("app.worker.tts_worker.settings") as mock_settings, \
             patch("app.worker.tts_worker.synthesize_tts") as mock_synth:
            mock_synth.run.side_effect = RuntimeError("Synthesis failed")
            mock_settings.get_silma_reference_audio.return_value = "/path/to/ref.wav"

            result = await handle_tts("nmt-child-001")

        assert result["segments"][0].get("tts_error") is not None
        assert result["metadata"]["failed"] == 1

    async def test_handler_raises_on_missing_job(self):
        with patch("app.worker.tts_worker.load_job", return_value=None):
            with pytest.raises(ValueError, match="not found"):
                await handle_tts("nonexistent")
