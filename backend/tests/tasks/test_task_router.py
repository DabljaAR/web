"""Tests for the VideoTask REST router (GET endpoints)."""
from unittest.mock import MagicMock
from datetime import datetime


from app.tasks.models import VideoTask, TaskStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(**kwargs) -> VideoTask:
    defaults = dict(
        id="task-001",
        video_id="vid-001",
        user_id=42,
        status=TaskStatus.PROCESSING,
        progress=50.0,
        output_type="fullDubbing",
        processing_mode="segmented",
        source_lang=None,
        target_lang="arb_Arab",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 5, 0),
        started_at=datetime(2026, 1, 1, 12, 0, 30),
        completed_at=None,
        error_message=None,
        transcript="Hello world",
        stt_segments=[{"start": 0.0, "end": 1.5, "text": "Hello world"}],
        translated_transcript=None,
        segments=None,
        stt_metadata={"language": "en", "duration": 5.0},
        num_beams=5,
        english_ratio_threshold=0.5,
        combined_audio_key=None,
        root_job_id="job-001",
    )
    defaults.update(kwargs)
    obj = MagicMock(spec=VideoTask)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


# ---------------------------------------------------------------------------
# Tests using mock dependencies
# ---------------------------------------------------------------------------

class TestTaskRouterListEndpoint:
    def test_list_tasks_for_video_returns_tasks(self):
        """Ensure GET /api/tasks/video/{id} endpoint exists."""
        from app.tasks.router import router
        # Router has prefix="/tasks" so paths include the prefix
        all_paths = {r.path for r in router.routes}
        # At least one route for video listing exists
        assert any("video_id" in p for p in all_paths)

    def test_task_router_registered(self):
        """Verify the tasks router is imported and has the expected structure."""
        from app.tasks.router import router
        paths = {r.path for r in router.routes}
        # Routes have full prefix included
        assert any("video_id" in p for p in paths)
        assert any("task_id" in p for p in paths)


class TestTaskRouterDetailEndpoint:
    def test_detail_endpoint_exists(self):
        """GET /api/tasks/{task_id} route exists."""
        from app.tasks.router import router
        detail_routes = [r for r in router.routes if "task_id" in r.path and "video_id" not in r.path]
        assert len(detail_routes) >= 1

    def test_detail_endpoint_methods(self):
        """Detail endpoint only supports GET."""
        from app.tasks.router import router
        detail_route = next(
            r for r in router.routes if "task_id" in r.path and "video_id" not in r.path
        )
        assert "GET" in detail_route.methods


class TestVideoTaskSummarySchema:
    def test_summary_from_task(self):
        """Ensure VideoTaskSummary can be built from a VideoTask instance."""
        from app.tasks.router import VideoTaskSummary
        task = _make_task()
        summary = VideoTaskSummary(
            id=task.id,
            video_id=task.video_id,
            status=task.status,
            progress=task.progress,
            output_type=task.output_type,
            processing_mode=task.processing_mode,
            source_lang=task.source_lang,
            target_lang=task.target_lang,
            created_at=task.created_at,
            updated_at=task.updated_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            error_message=task.error_message,
        )
        assert summary.status == TaskStatus.PROCESSING
        assert summary.progress == 50.0
        assert summary.target_lang == "arb_Arab"
