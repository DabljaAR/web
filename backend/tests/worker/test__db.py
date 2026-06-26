"""Unit tests for database helpers (_db.py).

These tests mock SQLAlchemy to avoid needing a real database.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.worker._db import (
    create_child_job,
    get_video_file_key,
    load_job,
    update_job_output,
)


def _make_mock_job(**overrides):
    job = MagicMock()
    attrs = {
        "id": "job-001",
        "video_id": "vid-001",
        "user_id": 42,
        "parent_job_id": None,
        "progress": 0.0,
        "retry_count": 0,
        "max_retries": 3,
        "error_message": None,
        "input_data": {},
        "output_data": {},
    }
    # Enum-like .value attribute
    for k in ("job_type", "status"):
        if k in overrides:
            val = overrides.pop(k)
            mock_enum = MagicMock()
            mock_enum.value = val
            attrs[k] = mock_enum
    attrs.update(overrides)
    for k, v in attrs.items():
        setattr(job, k, v)
    return job


class TestLoadJob:
    def test_load_job_returns_dict(self):
        mock_job = _make_mock_job(
            job_type="FULL_DUBBING_PIPELINE",
            status="QUEUED",
            input_data={"video_id": "vid-001"},
        )

        mock_session = MagicMock()
        mock_session.get.return_value = mock_job
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()

        with patch("app.worker._db._make_engine",
                   return_value=(mock_engine, MagicMock(return_value=mock_session))):
            result = load_job("job-001")

        assert result is not None
        assert result["id"] == "job-001"
        assert result["video_id"] == "vid-001"
        assert result["user_id"] == 42
        assert result["job_type"] == "FULL_DUBBING_PIPELINE"
        assert result["status"] == "QUEUED"
        assert result["input_data"]["video_id"] == "vid-001"

    def test_load_job_returns_none_for_missing(self):
        mock_session = MagicMock()
        mock_session.get.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()

        with patch("app.worker._db._make_engine",
                   return_value=(mock_engine, MagicMock(return_value=mock_session))):
            result = load_job("nonexistent")

        assert result is None

    def test_load_job_disposes_engine(self):
        mock_session = MagicMock()
        mock_session.get.return_value = _make_mock_job()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()

        with patch("app.worker._db._make_engine",
                   return_value=(mock_engine, MagicMock(return_value=mock_session))):
            load_job("job-001")

        mock_engine.dispose.assert_called_once()


class TestCreateChildJob:
    def test_create_child_job_inherits_fields(self):
        mock_parent = _make_mock_job(
            id="parent-001",
            user_id=42,
            video_id="vid-001",
            input_data={"target_lang": "arb_Arab"},
        )

        mock_session = MagicMock()
        mock_session.get.return_value = mock_parent
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()

        with patch("uuid.uuid4", return_value="new-child-id"), \
             patch("app.worker._db._make_engine",
                   return_value=(mock_engine, MagicMock(return_value=mock_session))):
            child_id = create_child_job(
                "parent-001",
                "STT_TRANSCRIBE",
                input_data={"extra": "data"},
            )

        assert child_id == "new-child-id"
        # Verify the child job was added with correct attrs
        added_job = mock_session.add.call_args[0][0]
        assert added_job.id == "new-child-id"
        assert added_job.parent_job_id == "parent-001"
        assert added_job.job_type.value == "STT_TRANSCRIBE"
        assert added_job.user_id == 42
        assert added_job.video_id == "vid-001"
        assert added_job.input_data["target_lang"] == "arb_Arab"
        assert added_job.input_data["extra"] == "data"
        mock_session.commit.assert_called_once()

    def test_create_child_job_raises_for_missing_parent(self):
        mock_session = MagicMock()
        mock_session.get.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()

        with patch("app.worker._db._make_engine",
                   return_value=(mock_engine, MagicMock(return_value=mock_session))):
            with pytest.raises(ValueError, match="Parent job missing-parent not found"):
                create_child_job("missing-parent", "STT_TRANSCRIBE")


class TestUpdateJobOutput:
    def test_update_job_output_saves_data(self):
        mock_job = _make_mock_job()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_job
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()

        with patch("app.worker._db._make_engine",
                   return_value=(mock_engine, MagicMock(return_value=mock_session))):
            update_job_output(
                "job-001",
                {"transcript": "hello"},
                status="COMPLETED",
                error=None,
            )

        assert mock_job.output_data == {"transcript": "hello"}
        assert mock_job.status.value == "COMPLETED"
        assert mock_job.error_message is None
        mock_session.commit.assert_called_once()

    def test_update_job_output_sets_error(self):
        mock_job = _make_mock_job()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_job
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()

        with patch("app.worker._db._make_engine",
                   return_value=(mock_engine, MagicMock(return_value=mock_session))):
            update_job_output(
                "job-001",
                {"status": "failed"},
                status="FAILED",
                error="GPU OOM",
            )

        assert mock_job.error_message == "GPU OOM"
        assert mock_job.status.value == "FAILED"

    def test_update_job_output_handles_missing(self):
        mock_session = MagicMock()
        mock_session.get.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()

        with patch("app.worker._db._make_engine",
                   return_value=(mock_engine, MagicMock(return_value=mock_session))):
            update_job_output("nonexistent", {"data": "val"})
        # Should not raise


class TestGetVideoFileKey:
    def test_returns_audio_path(self):
        mock_video = MagicMock()
        mock_video.audio_path = "audio/42/test.mp3"
        mock_video.file_path = "videos/42/test.mp4"

        mock_session = MagicMock()
        mock_session.get.return_value = mock_video
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()

        with patch("app.worker._db._make_engine",
                   return_value=(mock_engine, MagicMock(return_value=mock_session))):
            result = get_video_file_key("vid-001")

        assert result == "audio/42/test.mp3"

    def test_falls_back_to_file_path(self):
        mock_video = MagicMock()
        mock_video.audio_path = None
        mock_video.file_path = "videos/42/test.mp4"

        mock_session = MagicMock()
        mock_session.get.return_value = mock_video
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()

        with patch("app.worker._db._make_engine",
                   return_value=(mock_engine, MagicMock(return_value=mock_session))):
            result = get_video_file_key("vid-001")

        assert result == "videos/42/test.mp4"

    def test_returns_none_for_missing(self):
        mock_session = MagicMock()
        mock_session.get.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()

        with patch("app.worker._db._make_engine",
                   return_value=(mock_engine, MagicMock(return_value=mock_session))):
            result = get_video_file_key("nonexistent")

        assert result is None
