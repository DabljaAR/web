"""Unit tests for MediaServiceClient — all httpx calls are mocked."""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import httpx

from app.media_service.client import MediaServiceClient, MediaServiceError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int = 200, json_data: dict = None, raise_for_status=False):
    """Build a minimal httpx.Response-like mock."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    if raise_for_status:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def _async_client_mock(response: MagicMock):
    """Return a context-manager mock for httpx.AsyncClient that yields `response`."""
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    client.patch = AsyncMock(return_value=response)
    client.delete = AsyncMock(return_value=response)
    client.put = AsyncMock(return_value=response)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, client


# ---------------------------------------------------------------------------
# get_video
# ---------------------------------------------------------------------------

class TestGetVideo:
    @pytest.mark.asyncio
    async def test_returns_dict_on_200(self):
        resp = _mock_response(200, {"id": "vid-1", "user_id": 1, "status": "PENDING"})
        cm, _ = _async_client_mock(resp)
        with patch("httpx.AsyncClient", return_value=cm):
            result = await MediaServiceClient(base_url="http://mock").get_video("vid-1")
        assert result == {"id": "vid-1", "user_id": 1, "status": "PENDING"}

    @pytest.mark.asyncio
    async def test_returns_none_on_404(self):
        resp = _mock_response(404)
        cm, _ = _async_client_mock(resp)
        with patch("httpx.AsyncClient", return_value=cm):
            result = await MediaServiceClient(base_url="http://mock").get_video("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_raises_on_server_error(self):
        resp = _mock_response(500, raise_for_status=True)
        cm, _ = _async_client_mock(resp)
        with patch("httpx.AsyncClient", return_value=cm):
            with pytest.raises(httpx.HTTPStatusError):
                await MediaServiceClient(base_url="http://mock").get_video("vid-1")


# ---------------------------------------------------------------------------
# list_videos
# ---------------------------------------------------------------------------

class TestListVideos:
    @pytest.mark.asyncio
    async def test_passes_required_params(self):
        resp = _mock_response(200, {"items": [], "total": 0, "page": 1, "size": 10, "pages": 0})
        cm, mock_client = _async_client_mock(resp)
        with patch("httpx.AsyncClient", return_value=cm):
            result = await MediaServiceClient(base_url="http://mock").list_videos(
                user_id=42, page=1, limit=10
            )
        call_kwargs = mock_client.get.call_args
        assert call_kwargs[1]["params"]["user_id"] == 42
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_optional_filters_included_when_set(self):
        resp = _mock_response(200, {"items": [], "total": 0, "page": 1, "size": 5, "pages": 0})
        cm, mock_client = _async_client_mock(resp)
        with patch("httpx.AsyncClient", return_value=cm):
            await MediaServiceClient(base_url="http://mock").list_videos(
                user_id=1, search="test", status="COMPLETED", media_type="VIDEO"
            )
        params = mock_client.get.call_args[1]["params"]
        assert params["search"] == "test"
        assert params["status"] == "COMPLETED"
        assert params["media_type"] == "VIDEO"

    @pytest.mark.asyncio
    async def test_optional_filters_omitted_when_none(self):
        resp = _mock_response(200, {"items": [], "total": 0, "page": 1, "size": 10, "pages": 0})
        cm, mock_client = _async_client_mock(resp)
        with patch("httpx.AsyncClient", return_value=cm):
            await MediaServiceClient(base_url="http://mock").list_videos(user_id=1)
        params = mock_client.get.call_args[1]["params"]
        assert "search" not in params
        assert "status" not in params


# ---------------------------------------------------------------------------
# create_video
# ---------------------------------------------------------------------------

class TestCreateVideo:
    @pytest.mark.asyncio
    async def test_returns_created_video(self):
        payload = {"id": "new-vid", "user_id": 1, "title": "My Video", "file_path": "videos/1/v.mp4"}
        resp = _mock_response(201, payload)
        cm, mock_client = _async_client_mock(resp)
        with patch("httpx.AsyncClient", return_value=cm):
            result = await MediaServiceClient(base_url="http://mock").create_video(payload)
        mock_client.post.assert_called_once()
        assert result["id"] == "new-vid"

    @pytest.mark.asyncio
    async def test_raises_on_conflict(self):
        resp = _mock_response(409, raise_for_status=True)
        cm, _ = _async_client_mock(resp)
        with patch("httpx.AsyncClient", return_value=cm):
            with pytest.raises(httpx.HTTPStatusError):
                await MediaServiceClient(base_url="http://mock").create_video({"id": "dup"})


# ---------------------------------------------------------------------------
# delete_video
# ---------------------------------------------------------------------------

class TestDeleteVideo:
    @pytest.mark.asyncio
    async def test_returns_true_on_200(self):
        resp = _mock_response(200, {"status": "ok"})
        cm, _ = _async_client_mock(resp)
        with patch("httpx.AsyncClient", return_value=cm):
            result = await MediaServiceClient(base_url="http://mock").delete_video("vid-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_404(self):
        resp = _mock_response(404)
        cm, _ = _async_client_mock(resp)
        with patch("httpx.AsyncClient", return_value=cm):
            result = await MediaServiceClient(base_url="http://mock").delete_video("ghost")
        assert result is False


# ---------------------------------------------------------------------------
# presign_url
# ---------------------------------------------------------------------------

class TestPresignUrl:
    @pytest.mark.asyncio
    async def test_returns_url_string(self):
        resp = _mock_response(200, {"url": "https://s3.example.com/signed?token=abc"})
        cm, mock_client = _async_client_mock(resp)
        with patch("httpx.AsyncClient", return_value=cm):
            url = await MediaServiceClient(base_url="http://mock").presign_url("videos/1/v.mp4")
        assert url == "https://s3.example.com/signed?token=abc"

    @pytest.mark.asyncio
    async def test_raises_when_url_missing_from_response(self):
        resp = _mock_response(200, {"url": ""})
        cm, _ = _async_client_mock(resp)
        with patch("httpx.AsyncClient", return_value=cm):
            with pytest.raises(MediaServiceError):
                await MediaServiceClient(base_url="http://mock").presign_url("key")

    @pytest.mark.asyncio
    async def test_put_method_passes_content_type(self):
        resp = _mock_response(200, {"url": "https://s3.example.com/put?token=xyz"})
        cm, mock_client = _async_client_mock(resp)
        with patch("httpx.AsyncClient", return_value=cm):
            url = await MediaServiceClient(base_url="http://mock").presign_url(
                "audio/1/a.mp3", method="PUT", content_type="audio/mpeg"
            )
        body = mock_client.post.call_args[1]["json"]
        assert body["method"] == "PUT"
        assert body["content_type"] == "audio/mpeg"
        assert url == "https://s3.example.com/put?token=xyz"


# ---------------------------------------------------------------------------
# upload_file
# ---------------------------------------------------------------------------

class TestUploadFile:
    @pytest.mark.asyncio
    async def test_presigns_then_puts(self, tmp_path):
        test_file = tmp_path / "video.mp4"
        test_file.write_bytes(b"fake video content")

        presign_resp = _mock_response(200, {"url": "https://s3.example.com/put"})
        put_resp = _mock_response(200)

        presign_cm, presign_client = _async_client_mock(presign_resp)
        put_cm, put_client = _async_client_mock(put_resp)

        call_count = 0

        def client_factory(**kwargs):
            nonlocal call_count
            call_count += 1
            return presign_cm if call_count == 1 else put_cm

        with patch("httpx.AsyncClient", side_effect=client_factory):
            await MediaServiceClient(base_url="http://mock").upload_file(
                test_file, key="videos/1/v.mp4", content_type="video/mp4"
            )

        put_client.put.assert_called_once()
        put_args = put_client.put.call_args
        assert put_args[0][0] == "https://s3.example.com/put"
        assert put_args[1]["headers"]["Content-Type"] == "video/mp4"


# ---------------------------------------------------------------------------
# download_file
# ---------------------------------------------------------------------------

class TestDownloadFile:
    @pytest.mark.asyncio
    async def test_returns_true_and_writes_file(self, tmp_path):
        dest = tmp_path / "output.mp3"

        presign_resp = _mock_response(200, {"url": "https://s3.example.com/get"})
        presign_cm, _ = _async_client_mock(presign_resp)

        stream_resp = MagicMock()
        stream_resp.status_code = 200
        stream_resp.raise_for_status.return_value = None

        async def _fake_iter_bytes():
            yield b"chunk1"
            yield b"chunk2"

        stream_resp.aiter_bytes = _fake_iter_bytes

        stream_cm_inner = MagicMock()
        stream_cm_inner.__aenter__ = AsyncMock(return_value=stream_resp)
        stream_cm_inner.__aexit__ = AsyncMock(return_value=False)

        stream_client = MagicMock()
        stream_client.stream.return_value = stream_cm_inner
        stream_outer_cm = MagicMock()
        stream_outer_cm.__aenter__ = AsyncMock(return_value=stream_client)
        stream_outer_cm.__aexit__ = AsyncMock(return_value=False)

        call_count = 0

        def client_factory(**kwargs):
            nonlocal call_count
            call_count += 1
            return presign_cm if call_count == 1 else stream_outer_cm

        with patch("httpx.AsyncClient", side_effect=client_factory):
            result = await MediaServiceClient(base_url="http://mock").download_file(
                "audio/1/a.mp3", dest
            )

        assert result is True
        assert dest.exists()
        assert dest.read_bytes() == b"chunk1chunk2"

    @pytest.mark.asyncio
    async def test_returns_false_on_404(self, tmp_path):
        dest = tmp_path / "output.mp3"

        presign_resp = _mock_response(200, {"url": "https://s3.example.com/get"})
        presign_cm, _ = _async_client_mock(presign_resp)

        stream_resp = MagicMock()
        stream_resp.status_code = 404

        stream_cm_inner = MagicMock()
        stream_cm_inner.__aenter__ = AsyncMock(return_value=stream_resp)
        stream_cm_inner.__aexit__ = AsyncMock(return_value=False)

        stream_client = MagicMock()
        stream_client.stream.return_value = stream_cm_inner
        stream_outer_cm = MagicMock()
        stream_outer_cm.__aenter__ = AsyncMock(return_value=stream_client)
        stream_outer_cm.__aexit__ = AsyncMock(return_value=False)

        call_count = 0

        def client_factory(**kwargs):
            nonlocal call_count
            call_count += 1
            return presign_cm if call_count == 1 else stream_outer_cm

        with patch("httpx.AsyncClient", side_effect=client_factory):
            result = await MediaServiceClient(base_url="http://mock").download_file(
                "audio/1/missing.mp3", dest
            )

        assert result is False
        assert not dest.exists()
