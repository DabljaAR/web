"""Unit tests for the NMT worker handler."""
from unittest.mock import MagicMock, patch

import pytest

from app.worker.nmt_worker import create_worker, handle_nmt


class TestNmtWorkerHandler:
    def test_create_worker_configures_handler(self):
        worker = create_worker("amqp://localhost/", concurrency=2)
        assert worker._worker_name == "nmt"
        assert "job.start.nmt" in worker._handlers

    async def test_handler_translates_segments(self):
        stt_output = {
            "segments": [
                {"start": 0.0, "end": 2.5, "text": "Hello world"},
                {"start": 2.5, "end": 5.0, "text": "This is a test"},
            ],
        }
        stt_job = {
            "id": "stt-child-001",
            "video_id": "vid-001",
            "user_id": 42,
            "input_data": {
                "source_lang": "en",
                "target_lang": "arb_Arab",
                "task_id": "task-001",
            },
            "output_data": stt_output,
        }

        def fake_translate(text, src, tgt, max_len, **kw):
            return f"TRANS:{text}"

        def fake_adjust(translated_text, original_text, **kw):
            return translated_text.replace("TRANS:", "")

        with patch("app.worker.nmt_worker.load_job", return_value=stt_job), \
             patch("app.worker.nmt_worker.create_child_job", return_value="nmt-child-001"), \
             patch("app.worker.nmt_worker.update_job_output") as mock_update, \
             patch("app.worker.nmt_worker.translator") as mock_translator, \
             patch("app.worker.nmt_worker.settings") as mock_settings:
            mock_translator._translate_item.side_effect = fake_translate
            mock_settings.NMT_LENGTH_ADJUST_ENABLED = False

            result = await handle_nmt("stt-child-001")

        assert result["_result_job_id"] == "nmt-child-001"
        assert result["status"] == "completed"
        assert len(result["segments"]) == 2
        assert result["segments"][0]["translated_text"] == "TRANS:Hello world"
        assert result["segments"][1]["translated_text"] == "TRANS:This is a test"
        assert result["translated_transcript"] == "TRANS:Hello world TRANS:This is a test"
        mock_update.assert_called()

    async def test_handler_handles_empty_segments(self):
        stt_job = {
            "id": "stt-child-001",
            "video_id": "vid-001",
            "user_id": 42,
            "input_data": {"source_lang": "en", "target_lang": "arb_Arab"},
            "output_data": {"segments": []},
        }

        with patch("app.worker.nmt_worker.load_job", return_value=stt_job), \
             patch("app.worker.nmt_worker.create_child_job", return_value="nmt-child-001"), \
             patch("app.worker.nmt_worker.update_job_output"):
            result = await handle_nmt("stt-child-001")

        assert result["status"] == "completed"
        assert result["segments"] == []

    async def test_handler_raises_on_missing_job(self):
        with patch("app.worker.nmt_worker.load_job", return_value=None):
            with pytest.raises(ValueError, match="not found"):
                await handle_nmt("nonexistent")

    async def test_handler_applies_length_adjustment(self):
        stt_output = {
            "segments": [
                {"start": 0.0, "end": 2.5, "text": "Hello world"},
            ],
        }
        stt_job = {
            "id": "stt-child-001",
            "video_id": "vid-001",
            "user_id": 42,
            "input_data": {"source_lang": "en", "target_lang": "arb_Arab"},
            "output_data": stt_output,
        }

        with patch("app.worker.nmt_worker.load_job", return_value=stt_job), \
             patch("app.worker.nmt_worker.create_child_job", return_value="nmt-child-001"), \
             patch("app.worker.nmt_worker.update_job_output"), \
             patch("app.worker.nmt_worker.translator") as mock_translator, \
             patch("app.worker.nmt_worker.settings") as mock_settings, \
             patch("app.worker.nmt_worker.adjust_ar") as mock_adjust:
            mock_translator._translate_item.return_value = "مرحبا بالعالم"
            mock_settings.NMT_LENGTH_ADJUST_ENABLED = True
            mock_settings.NMT_LENGTH_ADJUST_SCALE = 0.9
            mock_settings.NMT_LENGTH_ADJUST_MAX_ITERS = 5
            mock_settings.GROQ_API_KEY = "test-key"
            mock_settings.GROQ_MODEL = "llama-test"
            mock_adjust.return_value = "مرحبا بالعالم المعدل"

            result = await handle_nmt("stt-child-001")

        assert result["segments"][0]["translated_text"] == "مرحبا بالعالم المعدل"
        mock_adjust.assert_called_once()

    async def test_handler_falls_back_on_translation_error(self):
        stt_output = {
            "segments": [
                {"start": 0.0, "end": 2.5, "text": "Hello"},
            ],
        }
        stt_job = {
            "id": "stt-child-001",
            "video_id": "vid-001",
            "user_id": 42,
            "input_data": {"source_lang": "en", "target_lang": "arb_Arab"},
            "output_data": stt_output,
        }

        with patch("app.worker.nmt_worker.load_job", return_value=stt_job), \
             patch("app.worker.nmt_worker.create_child_job", return_value="nmt-child-001"), \
             patch("app.worker.nmt_worker.update_job_output"), \
             patch("app.worker.nmt_worker.translator") as mock_translator, \
             patch("app.worker.nmt_worker.settings") as mock_settings:
            mock_translator._translate_item.side_effect = RuntimeError("Model OOM")
            mock_settings.NMT_LENGTH_ADJUST_ENABLED = False

            result = await handle_nmt("stt-child-001")

        # Falls back to original text
        assert result["segments"][0]["translated_text"] == "Hello"
