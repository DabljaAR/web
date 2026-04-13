"""Unit tests for NMT Celery tasks (chord/group architecture)."""
from unittest.mock import patch


class TestNmtCombineResults:
    """Test the chord callback that merges all segment results."""

    def _make_segment_result(self, i: int, status: str = "completed") -> dict:
        return {
            "segment_id": i,
            "job_id": "job-nmt-001",
            "original_text": f"original {i}",
            "translated_text": f"مترجم {i}",
            "start": float(i),
            "end": float(i + 1),
            "source_lang": "en",
            "target_lang": "arb_Arab",
            "status": status,
        }

    def test_sorts_segments_by_id(self):
        """nmt_combine_results must reorder segments by segment_id."""
        from app.jobs.tasks.nmt import nmt_combine_results

        shuffled = [
            self._make_segment_result(2),
            self._make_segment_result(0),
            self._make_segment_result(1),
        ]

        with patch("app.jobs.tasks.nmt.BaseJobTask._patch_job"), \
             patch("app.jobs.tasks.nmt.BaseJobTask._patch_task"):
            result = nmt_combine_results.run(
                shuffled,
                job_id="job-001",
                task_id=None,
                video_id="vid-001",
                full_transcript="original 0 original 1 original 2",
                resolved_source_lang="eng_Latn",
                resolved_target_lang="arb_Arab",
                output_type="captionsAndTranslation",
            )

        segs = result["segments"]
        assert segs[0]["original_text"] == "original 0"
        assert segs[1]["original_text"] == "original 1"
        assert segs[2]["original_text"] == "original 2"

    def test_builds_translated_transcript(self):
        """Translated transcript is concatenation of all segment translated_text."""
        from app.jobs.tasks.nmt import nmt_combine_results

        segments = [self._make_segment_result(i) for i in range(3)]

        with patch("app.jobs.tasks.nmt.BaseJobTask._patch_job"), \
             patch("app.jobs.tasks.nmt.BaseJobTask._patch_task"):
            result = nmt_combine_results.run(
                segments,
                job_id="job-002",
                task_id=None,
                video_id="vid-002",
                full_transcript="",
                resolved_source_lang="eng_Latn",
                resolved_target_lang="arb_Arab",
                output_type="fullDubbing",
            )

        expected = "مترجم 0 مترجم 1 مترجم 2"
        assert result["translated_transcript"] == expected

    def test_captions_and_translation_marks_task_completed(self):
        """captionsAndTranslation should set TaskStatus.COMPLETED on VideoTask."""
        from app.jobs.tasks.nmt import nmt_combine_results
        from app.tasks.models import TaskStatus

        task_patch_calls = []

        def capture(*args, **kwargs):
            task_patch_calls.append((args, kwargs))

        with patch("app.jobs.tasks.nmt.BaseJobTask._patch_job"), \
             patch("app.jobs.tasks.nmt.BaseJobTask._patch_task", side_effect=capture):
            nmt_combine_results.run(
                [self._make_segment_result(0)],
                job_id="job-003",
                task_id="task-003",
                video_id="vid-003",
                full_transcript="",
                resolved_source_lang="eng_Latn",
                resolved_target_lang="arb_Arab",
                output_type="captionsAndTranslation",
            )

        assert task_patch_calls
        status = task_patch_calls[-1][0][1]
        assert status == TaskStatus.COMPLETED

    def test_full_dubbing_marks_task_processing(self):
        """fullDubbing should leave VideoTask as PROCESSING (TTS still running)."""
        from app.jobs.tasks.nmt import nmt_combine_results
        from app.tasks.models import TaskStatus

        task_patch_calls = []

        def capture(*args, **kwargs):
            task_patch_calls.append((args, kwargs))

        with patch("app.jobs.tasks.nmt.BaseJobTask._patch_job"), \
             patch("app.jobs.tasks.nmt.BaseJobTask._patch_task", side_effect=capture):
            nmt_combine_results.run(
                [self._make_segment_result(0)],
                job_id="job-004",
                task_id="task-004",
                video_id="vid-004",
                full_transcript="",
                resolved_source_lang="eng_Latn",
                resolved_target_lang="arb_Arab",
                output_type="fullDubbing",
            )

        assert task_patch_calls
        status = task_patch_calls[-1][0][1]
        assert status == TaskStatus.PROCESSING

    def test_failed_segment_preserved(self):
        """Segment with status=failed should be included in output with original text."""
        from app.jobs.tasks.nmt import nmt_combine_results

        failed_seg = self._make_segment_result(0, status="failed")
        failed_seg["translated_text"] = "original 0"  # fallback to original

        with patch("app.jobs.tasks.nmt.BaseJobTask._patch_job"), \
             patch("app.jobs.tasks.nmt.BaseJobTask._patch_task"):
            result = nmt_combine_results.run(
                [failed_seg],
                job_id="job-005",
                task_id=None,
                video_id="vid-005",
                full_transcript="",
                resolved_source_lang="eng_Latn",
                resolved_target_lang="arb_Arab",
                output_type="captionsAndTranslation",
            )

        assert result["segments"][0]["translated_text"] == "original 0"


class TestNmtTranslateSegment:
    """Test per-segment translation with fallback behavior."""

    def test_fallback_on_translation_failure(self):
        """If translator raises, segment falls back to original text."""
        from app.jobs.tasks.nmt import nmt_translate_segment

        with patch("app.jobs.tasks.nmt.translator") as mock_translator:
            mock_translator._translate_item.side_effect = RuntimeError("model offline")

            result = nmt_translate_segment.run(
                segment_id=0,
                job_id="job-seg-001",
                text="Hello world",
                start=0.0,
                end=1.0,
                source_lang="eng_Latn",
                target_lang="arb_Arab",
            )

        assert result["translated_text"] == "Hello world"
        assert result["status"] == "failed"

    def test_successful_translation(self):
        """Successful translation returns translated_text."""
        from app.jobs.tasks.nmt import nmt_translate_segment

        with patch("app.jobs.tasks.nmt.translator") as mock_translator:
            mock_translator._translate_item.return_value = "مرحبا بالعالم"

            result = nmt_translate_segment.run(
                segment_id=1,
                job_id="job-seg-002",
                text="Hello world",
                start=0.0,
                end=1.5,
                source_lang="eng_Latn",
                target_lang="arb_Arab",
            )

        assert result["translated_text"] == "مرحبا بالعالم"
        assert result["status"] == "completed"
        assert result["segment_id"] == 1
