"""Unit tests for pipeline Celery tasks (stt_transcribe flow)."""
from unittest.mock import MagicMock, AsyncMock, patch


class TestSttTranscribeOutputRouting:
    """Verify stt_transcribe routes to NMT or short-circuits based on output_type."""

    def _make_stt_task(self):
        """Build a minimal mock of the stt_transcribe Celery task instance."""
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
            # Simulate DB returning a job row with captionsOnly
            mock_engine = MagicMock()
            mock_session = MagicMock()
            mock_job_row = MagicMock()
            mock_job_row.input_data = {"output_type": "captionsOnly", "task_id": "task-001"}
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session.get = MagicMock(return_value=mock_job_row)
            mock_make_db.return_value = (mock_engine, MagicMock(return_value=mock_session))

            # _create_next_job should never be called
            assert not mock_create_next.called

    def test_nmt_required_output_types(self):
        """fullDubbing, captionsAndTranslation, translationAndTTS all require NMT."""
        NMT_REQUIRED = {"captionsAndTranslation", "translationAndTTS", "fullDubbing"}
        assert "captionsOnly" not in NMT_REQUIRED
        for ot in NMT_REQUIRED:
            assert ot in NMT_REQUIRED

    def test_tts_combine_imports(self):
        """tts_combine_results and tts_synthesize_segment are importable tasks."""
        from app.jobs.tasks.pipeline import tts_combine_results, tts_synthesize_segment
        assert callable(tts_combine_results)
        assert callable(tts_synthesize_segment)


class TestTtsCombineResults:
    def test_combine_sorts_by_segment_id(self):
        """tts_combine_results must sort segments by segment_id regardless of input order."""
        from app.jobs.tasks.pipeline import tts_combine_results
        from unittest.mock import patch

        shuffled_results = [
            {"segment_id": 2, "start": 2.0, "end": 3.0, "tts_key": "k2", "audio_url": None},
            {"segment_id": 0, "start": 0.0, "end": 1.0, "tts_key": "k0", "audio_url": None},
            {"segment_id": 1, "start": 1.0, "end": 2.0, "tts_key": "k1", "audio_url": None},
        ]

        mock_storage = MagicMock()
        mock_storage.download = AsyncMock(return_value=False)

        # get_storage_service is imported locally inside tts_combine_results
        with patch("app.media.storage.get_storage_service", return_value=mock_storage), \
             patch("app.jobs.tasks.pipeline.BaseJobTask._patch_job"), \
             patch("app.jobs.tasks.pipeline.BaseJobTask._patch_task"), \
             patch("app.jobs.tasks.pipeline.BaseJobTask._make_db") as mock_make_db, \
             patch("subprocess.run") as mock_subprocess, \
             patch("asyncio.new_event_loop") as mock_loop_factory:
            mock_make_db.return_value = (MagicMock(), MagicMock(return_value=MagicMock()))
            mock_subprocess.return_value.returncode = 1  # force skip ffmpeg merge
            mock_loop = MagicMock()
            mock_loop.run_until_complete = MagicMock(return_value=False)
            mock_loop_factory.return_value = mock_loop

            result = tts_combine_results.run(
                shuffled_results,
                job_id="job-tts-001",
                task_id=None,
                video_id="vid-001",
                ref_clip_minio_key=None,
                metadata={},
                output_type="fullDubbing",
            )

        assert result["segments"][0]["tts_key"] == "k0"
        assert result["segments"][1]["tts_key"] == "k1"
        assert result["segments"][2]["tts_key"] == "k2"

    def test_combine_marks_failed_when_no_audio(self):
        """tts_combine_results marks job FAILED if all segments failed."""
        from app.jobs.tasks.pipeline import tts_combine_results
        from app.jobs.models import JobStatus

        failed_results = [
            {"segment_id": 0, "start": 0.0, "end": 1.0,
             "tts_key": None, "audio_url": None, "tts_error": "synth error"},
        ]

        patched_job_calls = []

        def capture_patch(*args, **kwargs):
            patched_job_calls.append((args, kwargs))

        with patch("app.jobs.tasks.pipeline.BaseJobTask._patch_job", side_effect=capture_patch), \
             patch("app.jobs.tasks.pipeline.BaseJobTask._patch_task"), \
             patch("app.jobs.tasks.pipeline.BaseJobTask._make_db") as mock_make_db, \
             patch("asyncio.new_event_loop"):
            mock_make_db.return_value = (MagicMock(), MagicMock(return_value=MagicMock()))

            tts_combine_results.run(
                failed_results,
                job_id="job-tts-fail",
                task_id=None,
                video_id="vid-fail",
                ref_clip_minio_key=None,
                metadata={},
                output_type="fullDubbing",
            )

        assert patched_job_calls
        last_call_status = patched_job_calls[-1][0][1]
        assert last_call_status == JobStatus.FAILED

    def test_combine_marks_failed_when_merge_errors(self):
        """tts_combine_results marks job/task FAILED when merge step raises."""
        from app.jobs.models import JobStatus
        from app.jobs.tasks.pipeline import tts_combine_results
        from app.tasks.models import TaskStatus

        results = [
            {"segment_id": 0, "start": 0.0, "end": 1.0, "tts_key": "tts/key.wav", "audio_url": None},
        ]

        patched_job_calls = []
        patched_task_calls = []

        def capture_job_patch(*args, **kwargs):
            patched_job_calls.append((args, kwargs))

        def capture_task_patch(*args, **kwargs):
            patched_task_calls.append((args, kwargs))

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.get = MagicMock(return_value=None)

        with patch("app.jobs.tasks.pipeline.BaseJobTask._patch_job", side_effect=capture_job_patch), \
             patch("app.jobs.tasks.pipeline.BaseJobTask._patch_task", side_effect=capture_task_patch), \
             patch("app.jobs.tasks.pipeline.BaseJobTask._make_db") as mock_make_db, \
             patch("app.dubbing.service.DubbingMergeService.merge_segments", new=AsyncMock(side_effect=PermissionError("Permission denied: 'uploads'"))), \
             patch("asyncio.new_event_loop"):
            mock_make_db.return_value = (MagicMock(), MagicMock(return_value=mock_session))

            tts_combine_results.run(
                results,
                job_id="job-tts-merge-fail",
                task_id="task-merge-fail",
                video_id="vid-merge-fail",
                ref_clip_minio_key=None,
                metadata={},
                output_type="fullDubbing",
            )

        assert patched_job_calls
        assert patched_job_calls[-1][0][1] == JobStatus.FAILED
        assert "Permission denied" in (patched_job_calls[-1][1].get("error_message") or "")

        assert patched_task_calls
        assert patched_task_calls[-1][0][1] == TaskStatus.FAILED
        assert "Permission denied" in (patched_task_calls[-1][1].get("error_message") or "")


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


class TestTtsProgressPatches:
    def test_tts_synthesize_segment_patches_progress(self):
        """TTS segment should emit progress updates during long synthesis."""
        from app.jobs.tasks.pipeline import tts_synthesize_segment

        mock_result = {
            "minio_key": "tts/job/segment_0.wav",
            "audio_url": "https://example.com/segment.wav",
        }

        with patch("app.jobs.tasks.pipeline.BaseJobTask._patch_job") as patch_job, \
             patch("app.jobs.tasks.pipeline.BaseJobTask._patch_task") as patch_task, \
             patch("app.jobs.celery_app.synthesize_tts") as mock_tts, \
             patch("app.media.storage.get_storage_service") as mock_storage_service, \
             patch("asyncio.new_event_loop") as mock_loop_factory:
            mock_tts.run.return_value = mock_result
            mock_storage = MagicMock()
            mock_storage.download = AsyncMock(return_value=True)
            mock_storage_service.return_value = mock_storage

            mock_loop = MagicMock()
            mock_loop.run_until_complete = MagicMock(return_value=True)
            mock_loop.close = MagicMock()
            mock_loop_factory.return_value = mock_loop

            tts_synthesize_segment.run(
                segment_id=0,
                job_id="tts-job",
                text="hello world",
                start=0.0,
                end=1.0,
                minio_segment_key="tts/job/segment_0.wav",
                ref_clip_minio_key="ref/key.wav",
                tts_job_id="tts-job",
                total_segments=None,
                task_id="task-1",
            )

        job_progress_values = [
            kwargs.get("progress")
            for _, kwargs in patch_job.call_args_list
            if kwargs.get("progress") is not None
        ]
        task_progress_values = [
            kwargs.get("progress")
            for _, kwargs in patch_task.call_args_list
            if kwargs.get("progress") is not None
        ]

        assert 60.0 in job_progress_values
        assert 85.0 in job_progress_values
        assert 60.0 in task_progress_values
        assert 85.0 in task_progress_values
