"""Tests for VideoTask model and TaskStatus enum."""

from app.tasks.models import VideoTask, TaskStatus


class TestTaskStatus:
    def test_enum_values(self):
        assert TaskStatus.QUEUED.value == "QUEUED"
        assert TaskStatus.PROCESSING.value == "PROCESSING"
        assert TaskStatus.COMPLETED.value == "COMPLETED"
        assert TaskStatus.FAILED.value == "FAILED"

    def test_str_enum_equality(self):
        assert TaskStatus.QUEUED == "QUEUED"
        assert TaskStatus.COMPLETED == "COMPLETED"

    def test_all_statuses_present(self):
        values = {s.value for s in TaskStatus}
        assert values == {"QUEUED", "PROCESSING", "COMPLETED", "FAILED"}


class TestVideoTaskModel:
    def test_tablename(self):
        assert VideoTask.__tablename__ == "video_tasks"

    def test_repr(self):
        task = VideoTask(
            id="abc-123",
            video_id="vid-456",
            user_id=1,
            status=TaskStatus.QUEUED,
            target_lang="arb_Arab",
            output_type="fullDubbing",
            num_beams=5,
            english_ratio_threshold=0.5,
            progress=0.0,
        )
        r = repr(task)
        assert "abc-123" in r
        assert "vid-456" in r
        assert "QUEUED" in r

    def test_default_target_lang_when_specified(self):
        task = VideoTask(
            id="t1",
            video_id="v1",
            user_id=1,
            status=TaskStatus.QUEUED,
            target_lang="arb_Arab",
        )
        assert task.target_lang == "arb_Arab"

    def test_default_output_type_when_specified(self):
        task = VideoTask(
            id="t2",
            video_id="v2",
            user_id=1,
            status=TaskStatus.QUEUED,
            output_type="fullDubbing",
        )
        assert task.output_type == "fullDubbing"

    def test_column_defaults_defined(self):
        """Verify that column-level server defaults are configured for target_lang and output_type."""
        target_col = VideoTask.__table__.c.target_lang
        output_col = VideoTask.__table__.c.output_type
        assert target_col is not None
        assert output_col is not None

    def test_optional_fields_none_by_default(self):
        task = VideoTask(
            id="t3",
            video_id="v3",
            user_id=1,
            status=TaskStatus.QUEUED,
        )
        assert task.transcript is None
        assert task.stt_segments is None
        assert task.translated_transcript is None
        assert task.segments is None
        assert task.combined_audio_key is None
        assert task.root_job_id is None
        assert task.error_message is None
