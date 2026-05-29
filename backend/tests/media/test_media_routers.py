"""
Integration tests for /api/videos/* endpoints.

All Rust media-service calls and DB writes are mocked. Authentication is
bypassed via FastAPI dependency_overrides.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.auth import get_current_user
from app.core.db import get_db
from app.media_service.client import MediaServiceClient


# ---------------------------------------------------------------------------
# Fake user
# ---------------------------------------------------------------------------

class _FakeUser:
    user_id = 99
    email = "user@test.com"
    username = "testuser"
    is_active = True


FAKE_USER = _FakeUser()

FAKE_VIDEO = {
    "id": "vid-abc",
    "user_id": 99,
    "title": "test.mp4",
    "original_filename": "test.mp4",
    "file_path": "videos/99/vid-abc.mp4",
    "thumbnail_path": None,
    "audio_path": None,
    "dubbed_video_path": None,
    "dubbing_metadata": None,
    "duration": None,
    "width": None,
    "height": None,
    "size_bytes": 1024,
    "format": None,
    "codec": None,
    "frame_rate": None,
    "media_type": "VIDEO",
    "status": "PENDING",
    "error_message": None,
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-01T00:00:00",
}


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

_UNSET = object()  # sentinel — distinguishes "not provided" from explicit None


def _make_mock_client(
    *,
    get_video=_UNSET,
    list_videos=None,
    create_video=None,
    delete_video=True,
    presign_url="https://s3.example.com/signed",
):
    client = MagicMock(spec=MediaServiceClient)
    client.get_video = AsyncMock(return_value=FAKE_VIDEO if get_video is _UNSET else get_video)
    client.list_videos = AsyncMock(return_value=list_videos or {
        "items": [], "total": 0, "page": 1, "size": 10,
        "pages": 0, "total_completed": 0, "total_failed": 0,
    })
    client.create_video = AsyncMock(return_value=create_video or FAKE_VIDEO)
    client.delete_video = AsyncMock(return_value=delete_video)
    client.presign_url = AsyncMock(return_value=presign_url)
    client.upload_file = AsyncMock(return_value=None)
    return client


def _make_mock_db():
    db = AsyncMock()
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=empty_result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def auth_client():
    """AsyncClient with auth dependency overridden. No DB override (tests manage it)."""
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c

    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def auth_db_client():
    """AsyncClient with both auth and DB overridden by mocks."""
    mock_db = _make_mock_db()

    async def _get_fake_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    app.dependency_overrides[get_db] = _get_fake_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c, mock_db

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Upload video
# ---------------------------------------------------------------------------

class TestUploadVideo:
    @pytest.mark.asyncio
    async def test_upload_video_returns_201_with_id(self, auth_client, tmp_path):
        mock_client = _make_mock_client()
        fake_tmp = tmp_path / "upload.mp4"
        fake_tmp.write_bytes(b"x")  # endpoint will unlink this

        with patch("app.api.media_routers.MediaServiceClient", return_value=mock_client), \
             patch("app.api.media_routers.process_video_task", new=AsyncMock()), \
             patch("app.api.media_routers._save_upload_to_tempfile",
                   new=AsyncMock(return_value=fake_tmp)):
            response = await auth_client.post(
                "/api/videos/upload",
                files={"file": ("clip.mp4", b"fake", "video/mp4")},
                data={"output_type": "uploadOnly"},
            )

        assert response.status_code == 201
        body = response.json()
        assert "id" in body
        assert body["status"] == "PENDING"
        mock_client.create_video.assert_called_once()
        mock_client.upload_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_video_rejects_non_video_content_type(self, auth_client):
        response = await auth_client.post(
            "/api/videos/upload",
            files={"file": ("doc.pdf", b"data", "application/pdf")},
        )
        assert response.status_code == 400
        assert "video" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_upload_audio_rejects_video_extension(self, auth_client):
        response = await auth_client.post(
            "/api/videos/upload/audio",
            files={"file": ("clip.mp4", b"data", "audio/mpeg")},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_audio_returns_201(self, auth_client, tmp_path):
        mock_client = _make_mock_client(
            create_video={**FAKE_VIDEO, "media_type": "AUDIO", "status": "PENDING"}
        )
        fake_tmp = tmp_path / "upload.mp3"
        fake_tmp.write_bytes(b"x")

        with patch("app.api.media_routers.MediaServiceClient", return_value=mock_client), \
             patch("app.api.media_routers.process_video_task", new=AsyncMock()), \
             patch("app.api.media_routers._save_upload_to_tempfile",
                   new=AsyncMock(return_value=fake_tmp)):
            response = await auth_client.post(
                "/api/videos/upload/audio",
                files={"file": ("recording.mp3", b"fake", "audio/mpeg")},
                data={"output_type": "uploadOnly"},
            )

        assert response.status_code == 201
        assert response.json()["status"] == "PENDING"


# ---------------------------------------------------------------------------
# Get single video
# ---------------------------------------------------------------------------

class TestGetVideo:
    @pytest.mark.asyncio
    async def test_returns_200_with_presigned_url(self, auth_db_client):
        client, db = auth_db_client
        mock_media = _make_mock_client()

        with patch("app.api.media_routers.MediaServiceClient", return_value=mock_media):
            response = await client.get("/api/videos/vid-abc")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == "vid-abc"
        assert body["url"] == "https://s3.example.com/signed"
        mock_media.presign_url.assert_called()

    @pytest.mark.asyncio
    async def test_returns_404_when_not_found(self, auth_db_client):
        client, _ = auth_db_client
        mock_media = _make_mock_client(get_video=None)

        with patch("app.api.media_routers.MediaServiceClient", return_value=mock_media):
            response = await client.get("/api/videos/ghost-id")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_403_for_another_users_video(self, auth_db_client):
        client, _ = auth_db_client
        other_video = {**FAKE_VIDEO, "user_id": 999}
        mock_media = _make_mock_client(get_video=other_video)

        with patch("app.api.media_routers.MediaServiceClient", return_value=mock_media):
            response = await client.get("/api/videos/vid-abc")

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_thumbnail_url_included_when_thumbnail_exists(self, auth_db_client):
        client, _ = auth_db_client
        video_with_thumb = {**FAKE_VIDEO, "thumbnail_path": "thumbnails/99/vid-abc.jpg"}

        call_count = {"n": 0}

        async def presign_side_effect(key, **kwargs):
            call_count["n"] += 1
            return f"https://s3.example.com/{key}"

        mock_media = _make_mock_client(get_video=video_with_thumb)
        mock_media.presign_url = AsyncMock(side_effect=presign_side_effect)

        with patch("app.api.media_routers.MediaServiceClient", return_value=mock_media):
            response = await client.get("/api/videos/vid-abc")

        assert response.status_code == 200
        body = response.json()
        assert "thumbnail_url" in body
        assert "thumbnails/99/vid-abc.jpg" in (body["thumbnail_url"] or "")


# ---------------------------------------------------------------------------
# Delete video
# ---------------------------------------------------------------------------

class TestDeleteVideo:
    @pytest.mark.asyncio
    async def test_delete_own_video_returns_200(self, auth_client):
        mock_media = _make_mock_client(delete_video=True)

        with patch("app.api.media_routers.MediaServiceClient", return_value=mock_media):
            response = await auth_client.delete("/api/videos/vid-abc")

        assert response.status_code == 200
        mock_media.delete_video.assert_called_once_with("vid-abc")

    @pytest.mark.asyncio
    async def test_delete_other_users_video_returns_403(self, auth_client):
        other_video = {**FAKE_VIDEO, "user_id": 999}
        mock_media = _make_mock_client(get_video=other_video)

        with patch("app.api.media_routers.MediaServiceClient", return_value=mock_media):
            response = await auth_client.delete("/api/videos/vid-abc")

        assert response.status_code == 403
        mock_media.delete_video.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_video_returns_404(self, auth_client):
        mock_media = _make_mock_client(get_video=None)

        with patch("app.api.media_routers.MediaServiceClient", return_value=mock_media):
            response = await auth_client.delete("/api/videos/ghost")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# List videos
# ---------------------------------------------------------------------------

class TestListVideos:
    @pytest.mark.asyncio
    async def test_returns_paginated_response(self, auth_db_client):
        client, _ = auth_db_client
        items = [{**FAKE_VIDEO, "id": f"vid-{i}"} for i in range(3)]
        mock_media = _make_mock_client(list_videos={
            "items": items, "total": 3, "page": 1,
            "size": 10, "pages": 1, "total_completed": 2, "total_failed": 0,
        })

        with patch("app.api.media_routers.MediaServiceClient", return_value=mock_media):
            response = await client.get("/api/videos/?page=1&limit=10")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3

    @pytest.mark.asyncio
    async def test_passes_filters_to_media_client(self, auth_db_client):
        client, _ = auth_db_client
        mock_media = _make_mock_client()

        with patch("app.api.media_routers.MediaServiceClient", return_value=mock_media):
            await client.get("/api/videos/?status=COMPLETED&mediaType=VIDEO&sortBy=date-asc")

        call_kw = mock_media.list_videos.call_args[1]
        assert call_kw["status"] == "COMPLETED"
        assert call_kw["media_type"] == "VIDEO"
        assert call_kw["sort_by"] == "date-asc"
        assert call_kw["user_id"] == FAKE_USER.user_id

    @pytest.mark.asyncio
    async def test_empty_list_returns_zero_total(self, auth_db_client):
        client, _ = auth_db_client
        mock_media = _make_mock_client()  # default returns empty items

        with patch("app.api.media_routers.MediaServiceClient", return_value=mock_media):
            response = await client.get("/api/videos/")

        assert response.status_code == 200
        assert response.json()["total"] == 0
        assert response.json()["items"] == []


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    @pytest.mark.asyncio
    async def test_returns_active_and_recent_keys(self, auth_db_client):
        client, _ = auth_db_client

        async def list_side_effect(**kwargs):
            status = kwargs.get("status", "")
            if "PENDING" in status or "PROCESSING" in status:
                return {"items": [{**FAKE_VIDEO, "status": "PROCESSING"}],
                        "total": 1, "page": 1, "size": 50, "pages": 1,
                        "total_completed": 0, "total_failed": 0}
            return {"items": [{**FAKE_VIDEO, "status": "COMPLETED"}],
                    "total": 1, "page": 1, "size": 10, "pages": 1,
                    "total_completed": 1, "total_failed": 0}

        mock_media = _make_mock_client()
        mock_media.list_videos = list_side_effect

        with patch("app.api.media_routers.MediaServiceClient", return_value=mock_media):
            response = await client.get("/api/videos/dashboard")

        assert response.status_code == 200
        body = response.json()
        assert "active" in body
        assert "recent" in body

    @pytest.mark.asyncio
    async def test_active_includes_processing_video(self, auth_db_client):
        client, _ = auth_db_client
        processing_video = {**FAKE_VIDEO, "status": "PROCESSING", "title": "My Vid"}

        async def list_side_effect(**kwargs):
            status = kwargs.get("status", "")
            if "PENDING" in status:
                return {"items": [processing_video], "total": 1, "page": 1,
                        "size": 50, "pages": 1, "total_completed": 0, "total_failed": 0}
            return {"items": [], "total": 0, "page": 1, "size": 10,
                    "pages": 0, "total_completed": 0, "total_failed": 0}

        mock_media = _make_mock_client()
        mock_media.list_videos = list_side_effect

        with patch("app.api.media_routers.MediaServiceClient", return_value=mock_media):
            response = await client.get("/api/videos/dashboard")

        body = response.json()
        assert any(item["name"] == "My Vid" for item in body["active"])
