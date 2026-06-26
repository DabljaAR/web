"""Integration test for RabbitMQ-native worker database helpers.

Tests ``app.worker._db`` functions against a real PostgreSQL database
running via docker-compose.test.yml.
"""

import json
from datetime import datetime, timezone

import pytest

from tests.integration.helpers import PG_DSN, new_id

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        "not config.getoption('--run-integration')",
        reason="Pass --run-integration to enable integration tests",
    ),
]


class TestLoadJob:
    def test_returns_job_as_dict(self, pg_cursor, pg_conn):
        job_id = new_id()
        now = datetime.now(timezone.utc)
        pg_cursor.execute(
            """
            INSERT INTO jobs (id, user_id, job_type, status, created_at, updated_at)
            VALUES (%s, 1, 'STT_TRANSCRIBE'::jobtype, 'COMPLETED'::jobstatus, %s, %s)
            """,
            (job_id, now, now),
        )
        pg_conn.commit()

        from app.worker._db import load_job

        result = load_job(job_id)

        assert result is not None
        assert result["id"] == job_id
        assert result["job_type"] == "STT_TRANSCRIBE"
        assert result["status"] == "COMPLETED"

    def test_returns_none_for_missing(self):
        from app.worker._db import load_job

        result = load_job("nonexistent-id")
        assert result is None

    def test_loads_video_id_and_user_id(self, pg_cursor, pg_conn):
        job_id = new_id()
        video_id = new_id()
        now = datetime.now(timezone.utc)
        pg_cursor.execute(
            """
            INSERT INTO videos (id, user_id, title, status, file_path, created_at, updated_at)
            VALUES (%s, 1, 'test', 'COMPLETED', 'test.mp4', %s, %s)
            """,
            (video_id, now, now),
        )
        pg_cursor.execute(
            """
            INSERT INTO jobs (id, user_id, video_id, job_type, status, created_at, updated_at)
            VALUES (%s, 42, %s, 'NMT_TRANSLATE'::jobtype, 'PROCESSING'::jobstatus, %s, %s)
            """,
            (job_id, video_id, now, now),
        )
        pg_conn.commit()

        from app.worker._db import load_job

        result = load_job(job_id)

        assert result["user_id"] == 42
        assert result["video_id"] == video_id


class TestCreateChildJob:
    def test_creates_child_inheriting_fields(self, pg_cursor, pg_conn):
        parent_id = new_id()
        video_id = new_id()
        now = datetime.now(timezone.utc)

        pg_cursor.execute(
            """
            INSERT INTO videos (id, user_id, title, status, file_path, created_at, updated_at)
            VALUES (%s, 1, 'test', 'COMPLETED', 'test.mp4', %s, %s)
            """,
            (video_id, now, now),
        )
        pg_cursor.execute(
            """
            INSERT INTO jobs (id, user_id, video_id, job_type, status, input_data, created_at, updated_at)
            VALUES (%s, 1, %s, 'FULL_DUBBING_PIPELINE'::jobtype, 'QUEUED'::jobstatus,
                    %s::jsonb, %s, %s)
            """,
            (parent_id, video_id, json.dumps({"key": "value"}), now, now),
        )
        pg_conn.commit()

        from app.worker._db import create_child_job

        child_id = create_child_job(parent_id, "STT_TRANSCRIBE", {"extra": "data"})

        assert child_id is not None
        pg_cursor.execute("SELECT * FROM jobs WHERE id = %s", (child_id,))
        child = dict(pg_cursor.fetchone())
        assert child["parent_job_id"] == parent_id
        assert child["job_type"] == "STT_TRANSCRIBE"
        assert child["user_id"] == 1
        assert child["video_id"] == video_id
        assert child["status"] == "QUEUED"

    def test_raises_for_missing_parent(self):
        from app.worker._db import create_child_job

        with pytest.raises(ValueError, match="Parent job .* not found"):
            create_child_job("nonexistent-id", "STT_TRANSCRIBE", {})


class TestUpdateJobOutput:
    def test_saves_output_data_and_status(self, pg_cursor, pg_conn):
        job_id = new_id()
        now = datetime.now(timezone.utc)
        pg_cursor.execute(
            """
            INSERT INTO jobs (id, user_id, job_type, status, created_at, updated_at)
            VALUES (%s, 1, 'STT_TRANSCRIBE'::jobtype, 'PROCESSING'::jobstatus, %s, %s)
            """,
            (job_id, now, now),
        )
        pg_conn.commit()

        from app.worker._db import update_job_output

        output_data = {"transcript": "hello", "segments": [{"start": 0.0, "end": 1.0}]}
        update_job_output(job_id, output_data, status="COMPLETED")

        pg_cursor.execute("SELECT status, output_data FROM jobs WHERE id = %s", (job_id,))
        row = pg_cursor.fetchone()
        assert row["status"] == "COMPLETED"
        assert row["output_data"]["transcript"] == "hello"

    def test_sets_error_message(self, pg_cursor, pg_conn):
        job_id = new_id()
        now = datetime.now(timezone.utc)
        pg_cursor.execute(
            """
            INSERT INTO jobs (id, user_id, job_type, status, created_at, updated_at)
            VALUES (%s, 1, 'STT_TRANSCRIBE'::jobtype, 'PROCESSING'::jobstatus, %s, %s)
            """,
            (job_id, now, now),
        )
        pg_conn.commit()

        from app.worker._db import update_job_output

        update_job_output(job_id, {}, status="FAILED", error="GPU out of memory")

        pg_cursor.execute("SELECT status, error_message FROM jobs WHERE id = %s", (job_id,))
        row = pg_cursor.fetchone()
        assert row["status"] == "FAILED"
        assert row["error_message"] == "GPU out of memory"


class TestGetVideoFileKey:
    def test_returns_audio_path(self, pg_cursor, pg_conn):
        video_id = new_id()
        now = datetime.now(timezone.utc)
        pg_cursor.execute(
            """
            INSERT INTO videos (id, user_id, title, status, file_path, audio_path, created_at, updated_at)
            VALUES (%s, 1, 'test', 'COMPLETED', 'original.mp4', 'audio/test.mp3', %s, %s)
            """,
            (video_id, now, now),
        )
        pg_conn.commit()

        from app.worker._db import get_video_file_key

        key = get_video_file_key(video_id)
        assert key == "audio/test.mp3"

    def test_falls_back_to_file_path(self, pg_cursor, pg_conn):
        video_id = new_id()
        now = datetime.now(timezone.utc)
        pg_cursor.execute(
            """
            INSERT INTO videos (id, user_id, title, status, file_path, created_at, updated_at)
            VALUES (%s, 1, 'test', 'COMPLETED', 'videos/1/test.mp4', %s, %s)
            """,
            (video_id, now, now),
        )
        pg_conn.commit()

        from app.worker._db import get_video_file_key

        key = get_video_file_key(video_id)
        assert key == "videos/1/test.mp4"

    def test_returns_none_for_missing(self):
        from app.worker._db import get_video_file_key

        key = get_video_file_key("nonexistent-id")
        assert key is None
