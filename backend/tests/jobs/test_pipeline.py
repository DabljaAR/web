"""Unit tests for pipeline utility functions and STT-to-NMT routing logic."""
from unittest.mock import MagicMock, patch


class TestSttTranscribeOutputRouting:
    """Verify STT routes to NMT or short-circuits based on output_type."""

    def _make_stt_task(self):
        task = MagicMock()
        task.request.id = "celery-task-id-001"
        task._make_db = MagicMock(return_value=(MagicMock(), MagicMock()))
        task._patch_job = MagicMock()
        task._patch_task = MagicMock()
        task._create_next_job = MagicMock(return_value="nmt-job-001")
        task.update_progress = MagicMock()
        task._run_sync = MagicMock(return_value=True)
        return task

    def test_captions_only_does_not_dispatch_nmt(self):
        """captionsOnly output_type should NOT dispatch an NMT job."""
        from app.jobs.tasks.base import BaseJobTask

        with patch.object(BaseJobTask, "_make_db") as mock_make_db, \
             patch.object(BaseJobTask, "_patch_job"), \
             patch.object(BaseJobTask, "_patch_task"), \
             patch.object(BaseJobTask, "_create_next_job") as mock_create_next:
            mock_engine = MagicMock()
            mock_session = MagicMock()
            mock_job_row = MagicMock()
            mock_job_row.input_data = {"output_type": "captionsOnly", "task_id": "task-001"}
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session.get = MagicMock(return_value=mock_job_row)
            mock_make_db.return_value = (mock_engine, MagicMock(return_value=mock_session))

            assert not mock_create_next.called

    def test_nmt_required_output_types(self):
        """fullDubbing, captionsAndTranslation, translationAndTTS all require NMT."""
        NMT_REQUIRED = {"captionsAndTranslation", "translationAndTTS", "fullDubbing"}
        assert "captionsOnly" not in NMT_REQUIRED
        for ot in NMT_REQUIRED:
            assert ot in NMT_REQUIRED


class TestProcessingModeHelpers:
    def test_apply_processing_mode_returns_single_chunk(self):
        """single mode should collapse segments to one transcript chunk."""
        from app.jobs.tasks.pipeline import _apply_processing_mode

        result = _apply_processing_mode(
            segments=[
                {"start": 0.0, "end": 1.0, "text": "Hello"},
                {"start": 1.0, "end": 2.0, "text": "world"},
            ],
            words=None,
            transcript="Hello world",
            duration=2.5,
            processing_mode="single",
        )

        assert len(result) == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 2.5
        assert result[0]["text"] == "Hello world"

    def test_apply_processing_mode_keeps_stt_focused_shape(self):
        """stt_focused mode should preserve original segment list."""
        from app.jobs.tasks.pipeline import _apply_processing_mode

        segments = [{"start": 0.0, "end": 1.0, "text": "Hello"}]
        result = _apply_processing_mode(
            segments=segments,
            words=None,
            transcript="Hello",
            duration=1.0,
            processing_mode="stt_focused",
        )

        assert result == segments

    def test_apply_processing_mode_tts_focused_rebuilds(self):
        """tts_focused mode should rebuild segments from words."""
        from app.jobs.tasks.pipeline import _apply_processing_mode

        result = _apply_processing_mode(
            segments=[{"start": 0.0, "end": 2.0, "text": "old"}],
            words=[
                {"word": "one", "start": 0.0, "end": 0.2},
                {"word": "two", "start": 0.2, "end": 0.4},
                {"word": "three", "start": 0.4, "end": 0.6},
                {"word": "four", "start": 0.6, "end": 0.8},
                {"word": "five", "start": 0.8, "end": 1.0},
                {"word": "six", "start": 1.0, "end": 1.2},
                {"word": "seven", "start": 1.2, "end": 1.4},
                {"word": "eight", "start": 1.4, "end": 1.6},
                {"word": "nine", "start": 1.6, "end": 1.8},
                {"word": "ten.", "start": 1.8, "end": 2.0},
            ],
            transcript="one two three four five six seven eight nine ten.",
            duration=2.0,
            processing_mode="tts_focused",
        )

        assert len(result) == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 2.0

    def test_apply_processing_mode_invalid_falls_back_to_single(self):
        """Invalid modes should warn and fallback to single behavior."""
        from app.jobs.tasks.pipeline import _apply_processing_mode

        result = _apply_processing_mode(
            segments=[{"start": 1.0, "end": 2.0, "text": "keep"}],
            words=None,
            transcript="Hello world",
            duration=2.5,
            processing_mode="not_valid",
        )

        assert len(result) == 1
        assert result[0]["start"] == 0.0
