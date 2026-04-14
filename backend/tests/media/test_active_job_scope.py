"""Tests for history active-job scoping to latest VideoTask run."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.jobs.models import JobStatus
from app.media.service import VideoService


def test_get_user_videos_scopes_active_jobs_to_latest_task_root():
    """Old active jobs should not force processing when latest run has no active jobs."""
    db = AsyncMock()
    service = VideoService(db)

    service.storage.get_url = AsyncMock(return_value="https://example.com/file")

    video = SimpleNamespace(
        id="vid-1",
        user_id=1,
        title="Video",
        original_filename="v.mp4",
        file_path="videos/v.mp4",
        thumbnail_path=None,
        audio_path=None,
        duration=None,
        size_bytes=None,
        status="COMPLETED",
        media_type="VIDEO",
        created_at=None,
        updated_at=None,
    )

    # Latest task root is root-new; old active job belongs to root-old.
    latest_task = SimpleNamespace(video_id="vid-1", root_job_id="root-new", created_at=2)

    old_active = SimpleNamespace(
        id="old-child",
        video_id="vid-1",
        parent_job_id="root-old",
        status=JobStatus.PROCESSING,
        progress=30.0,
        output_data={},
        job_type=None,
        created_at=1,
    )
    latest_done = SimpleNamespace(
        id="new-child",
        video_id="vid-1",
        parent_job_id="root-new",
        status=JobStatus.COMPLETED,
        progress=100.0,
        output_data={},
        job_type=None,
        created_at=3,
    )

    # Scalar calls for totals.
    db.scalar.side_effect = [1, 1, 0]

    # execute() order in get_user_videos:
    # 1) paged videos, 2) jobs for page videos, 3) latest tasks.
    db.execute.side_effect = [
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [video])),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [old_active, latest_done])),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [latest_task])),
    ]

    resp = asyncio.run(service.get_user_videos(user_id=1, page=1, limit=10))
    item = resp["items"][0]

    assert item.has_active_job is False
    assert item.active_job_status is None


def test_get_user_videos_falls_back_when_latest_task_has_no_root():
    """If latest task has no root_job_id, active jobs should not be filtered out."""
    db = AsyncMock()
    service = VideoService(db)

    service.storage.get_url = AsyncMock(return_value="https://example.com/file")

    video = SimpleNamespace(
        id="vid-2",
        user_id=1,
        title="Video 2",
        original_filename="v2.mp4",
        file_path="videos/v2.mp4",
        thumbnail_path=None,
        audio_path=None,
        duration=None,
        size_bytes=None,
        status="COMPLETED",
        media_type="VIDEO",
        created_at=None,
        updated_at=None,
    )

    latest_task = SimpleNamespace(video_id="vid-2", root_job_id=None, created_at=10)

    active_job = SimpleNamespace(
        id="active-job",
        video_id="vid-2",
        parent_job_id="root-x",
        status=JobStatus.PROCESSING,
        progress=40.0,
        output_data={},
        job_type=None,
        created_at=11,
    )

    db.scalar.side_effect = [1, 1, 0]
    db.execute.side_effect = [
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [video])),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [active_job])),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [latest_task])),
    ]

    resp = asyncio.run(service.get_user_videos(user_id=1, page=1, limit=10))
    item = resp["items"][0]

    assert item.has_active_job is True
    assert item.active_job_status == JobStatus.PROCESSING.value
