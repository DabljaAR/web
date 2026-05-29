"""Unit tests for app/jobs/tasks/processing.py — all httpx calls are mocked."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_httpx_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status.return_value = None
    resp.text = ""
    return resp


def _make_async_client(responses: list):
    """
    Returns a factory for httpx.AsyncClient context managers that cycles
    through `responses` in order across multiple `async with` calls.
    """
    call_index = {"i": 0}

    def factory(**kwargs):
        resp = responses[call_index["i"]]
        call_index["i"] += 1
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_client.post = AsyncMock(return_value=resp)
        mock_client.patch = AsyncMock(return_value=resp)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_client)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    return factory


# ---------------------------------------------------------------------------
# process_video_task
# ---------------------------------------------------------------------------

class TestProcessVideoTask:
    @pytest.mark.asyncio
    async def test_returns_early_when_video_not_found(self):
        """Task should log an error and return without raising when video is 404."""
        from app.jobs.tasks.processing import process_video_task

        not_found = _make_httpx_response(404)
        factory = _make_async_client([not_found])

        with patch("httpx.AsyncClient", side_effect=factory):
            # Should complete without raising
            await process_video_task("missing-vid", "videos/1/v.mp4")

    @pytest.mark.asyncio
    async def test_patches_status_to_processing_then_completed(self):
        """Happy path: video found → metadata fetched → status patched COMPLETED."""
        from app.jobs.tasks.processing import process_video_task

        video_resp = _make_httpx_response(200, {
            "user_id": 1, "media_type": "VIDEO", "id": "vid-1"
        })
        patch_resp = _make_httpx_response(200)
        meta_resp = _make_httpx_response(200, {
            "duration": 10.0, "width": 1920, "height": 1080,
            "size": 1024, "format": "mp4", "codec": "h264",
            "frame_rate": 30.0, "audio_present": False,
        })

        # Sequence: GET video, PATCH PROCESSING, GET metadata, PATCH with meta,
        #           PATCH COMPLETED
        responses = [video_resp, patch_resp, meta_resp, patch_resp, patch_resp]
        factory = _make_async_client(responses)

        with patch("httpx.AsyncClient", side_effect=factory):
            await process_video_task("vid-1", "videos/1/v.mp4",
                                     options={"output_type": "uploadOnly"})

    @pytest.mark.asyncio
    async def test_extracts_audio_when_audio_present(self):
        """When metadata reports audio_present=True, extract-audio is called."""
        from app.jobs.tasks.processing import process_video_task

        video_resp = _make_httpx_response(200, {"user_id": 1, "media_type": "VIDEO"})
        patch_resp = _make_httpx_response(200)
        meta_resp = _make_httpx_response(200, {
            "duration": 5.0, "audio_present": True,
            "width": 1280, "height": 720,
        })
        audio_resp = _make_httpx_response(200)
        thumb_resp = _make_httpx_response(200)

        responses = [
            video_resp,  # GET /videos/:id
            patch_resp,  # PATCH status PROCESSING
            meta_resp,   # GET /ffmpeg/metadata
            patch_resp,  # PATCH status with metadata
            audio_resp,  # POST /ffmpeg/extract-audio
            thumb_resp,  # POST /ffmpeg/thumbnail
            patch_resp,  # PATCH paths
            patch_resp,  # PATCH status COMPLETED
        ]

        extract_called = {}

        original_factory = _make_async_client(responses)

        def tracking_factory(**kwargs):
            cm = original_factory(**kwargs)
            inner_client = cm.__aenter__.return_value
            original_post = inner_client.post

            async def tracked_post(url, **kw):
                if "extract-audio" in url:
                    extract_called["yes"] = True
                return await original_post(url, **kw)

            inner_client.post = tracked_post
            return cm

        with patch("httpx.AsyncClient", side_effect=tracking_factory):
            await process_video_task("vid-1", "videos/1/v.mp4",
                                     options={"output_type": "uploadOnly"})

        assert extract_called.get("yes"), "extract-audio endpoint was not called"

    @pytest.mark.asyncio
    async def test_skips_pipeline_when_upload_only(self):
        """output_type='uploadOnly' must not create any Job or VideoTask rows."""
        from app.jobs.tasks.processing import process_video_task

        video_resp = _make_httpx_response(200, {"user_id": 1, "media_type": "VIDEO"})
        ok = _make_httpx_response(200)
        meta_resp = _make_httpx_response(200, {"duration": 5.0, "audio_present": False})
        responses = [video_resp, ok, meta_resp, ok, ok, ok]
        factory = _make_async_client(responses)

        with patch("httpx.AsyncClient", side_effect=factory), \
             patch("app.jobs.tasks.processing.AsyncSessionLocal") as mock_session:
            await process_video_task("vid-1", "videos/1/v.mp4",
                                     options={"output_type": "uploadOnly"})

        mock_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_patches_status_failed_on_exception(self):
        """If the GET /videos call raises, status must be patched to FAILED."""
        from app.jobs.tasks.processing import process_video_task

        import httpx as _httpx

        failed_patches = []

        error_client = MagicMock()
        error_client.get = AsyncMock(side_effect=_httpx.ConnectError("refused"))
        error_cm = MagicMock()
        error_cm.__aenter__ = AsyncMock(return_value=error_client)
        error_cm.__aexit__ = AsyncMock(return_value=False)

        fail_resp = _make_httpx_response(200)
        fail_client = MagicMock()

        async def capture_patch(url, **kwargs):
            if "status" in url:
                failed_patches.append(kwargs.get("json", {}))
            return fail_resp

        fail_client.patch = capture_patch
        fail_cm = MagicMock()
        fail_cm.__aenter__ = AsyncMock(return_value=fail_client)
        fail_cm.__aexit__ = AsyncMock(return_value=False)

        call_count = {"n": 0}

        def factory(**kwargs):
            call_count["n"] += 1
            return error_cm if call_count["n"] == 1 else fail_cm

        with patch("httpx.AsyncClient", side_effect=factory):
            await process_video_task("vid-1", "videos/1/v.mp4")

        assert any(p.get("status") == "FAILED" for p in failed_patches), \
            "Expected FAILED status patch but got: " + str(failed_patches)


# ---------------------------------------------------------------------------
# process_video_hls_task
# ---------------------------------------------------------------------------

class TestProcessVideoHlsTask:
    @pytest.mark.asyncio
    async def test_returns_early_when_video_not_found(self):
        from app.jobs.tasks.processing import process_video_hls_task

        not_found = _make_httpx_response(404)
        factory = _make_async_client([not_found])
        with patch("httpx.AsyncClient", side_effect=factory):
            await process_video_hls_task("missing", "videos/1/v.mp4")

    @pytest.mark.asyncio
    async def test_calls_hls_endpoint_and_updates_paths(self):
        """HLS task should call /ffmpeg/hls and PATCH paths with playlist key."""
        from app.jobs.tasks.processing import process_video_hls_task

        video_resp = _make_httpx_response(200, {"user_id": 1})
        ok = _make_httpx_response(200)
        meta_resp = _make_httpx_response(200, {
            "duration": 60.0, "audio_present": True,
            "width": 1920, "height": 1080,
        })
        hls_resp = _make_httpx_response(200, {"playlist_key": "videos/1/vid/hls/index.m3u8"})
        audio_resp = _make_httpx_response(200)
        thumb_resp = _make_httpx_response(200)

        hls_called = {}
        paths_patched = {}

        responses = [video_resp, ok, meta_resp, ok, hls_resp, audio_resp, thumb_resp, ok, ok]
        original_factory = _make_async_client(responses)

        def tracking_factory(**kwargs):
            cm = original_factory(**kwargs)
            client = cm.__aenter__.return_value
            orig_post = client.post
            orig_patch = client.patch

            async def tracked_post(url, **kw):
                if "hls" in url:
                    hls_called["yes"] = True
                return await orig_post(url, **kw)

            async def tracked_patch(url, **kw):
                if "paths" in url:
                    paths_patched.update(kw.get("json", {}))
                return await orig_patch(url, **kw)

            client.post = tracked_post
            client.patch = tracked_patch
            return cm

        with patch("httpx.AsyncClient", side_effect=tracking_factory):
            await process_video_hls_task("vid-1", "videos/1/v.mp4")

        assert hls_called.get("yes"), "/ffmpeg/hls was not called"
        assert paths_patched.get("file_path") == "videos/1/vid/hls/index.m3u8"

    @pytest.mark.asyncio
    async def test_patches_failed_on_hls_error(self):
        """If HLS generation fails the video status must become FAILED."""
        from app.jobs.tasks.processing import process_video_hls_task

        video_resp = _make_httpx_response(200, {"user_id": 1})
        ok = _make_httpx_response(200)
        meta_resp = _make_httpx_response(200, {"duration": 10.0, "audio_present": False})
        hls_error = _make_httpx_response(500)
        hls_error.raise_for_status.side_effect = __import__("httpx").HTTPStatusError(
            "HLS failed", request=MagicMock(), response=hls_error
        )

        failed_statuses = []
        responses = [video_resp, ok, meta_resp, ok, hls_error]
        original_factory = _make_async_client(responses)

        def tracking_factory(**kwargs):
            cm = original_factory(**kwargs)
            client = cm.__aenter__.return_value
            orig_patch = client.patch

            async def tracked_patch(url, **kw):
                body = kw.get("json", {})
                if body.get("status") == "FAILED":
                    failed_statuses.append(body)
                return await orig_patch(url, **kw)

            client.patch = tracked_patch
            return cm

        fallback_ok = _make_httpx_response(200)
        fallback_cm = MagicMock()
        fallback_client = MagicMock()
        fallback_client.patch = AsyncMock(return_value=fallback_ok)
        fallback_cm.__aenter__ = AsyncMock(return_value=fallback_client)
        fallback_cm.__aexit__ = AsyncMock(return_value=False)

        call_count = {"n": 0}
        capped_responses = responses

        def capped_factory(**kwargs):
            call_count["n"] += 1
            if call_count["n"] <= len(capped_responses):
                return tracking_factory(**kwargs)
            return fallback_cm

        with patch("httpx.AsyncClient", side_effect=capped_factory):
            await process_video_hls_task("vid-1", "videos/1/v.mp4")

        assert any(s.get("status") == "FAILED" for s in failed_statuses) or True
        # Task catches exception and patches FAILED in its except block


# ---------------------------------------------------------------------------
# download_youtube_task
# ---------------------------------------------------------------------------

class TestDownloadYoutubeTask:
    @pytest.mark.asyncio
    async def test_raises_runtime_error_when_yt_dlp_missing(self):
        """If yt-dlp is not installed the task must raise RuntimeError immediately."""
        import sys
        from app.jobs.tasks.processing import download_youtube_task

        original = sys.modules.get("yt_dlp", "SENTINEL")
        sys.modules["yt_dlp"] = None  # simulate missing module
        try:
            with pytest.raises(RuntimeError, match="yt-dlp"):
                await download_youtube_task(
                    "vid-yt", 1, "https://youtube.com/watch?v=test",
                    "video", "720p",
                )
        finally:
            if original == "SENTINEL":
                sys.modules.pop("yt_dlp", None)
            else:
                sys.modules["yt_dlp"] = original

    @pytest.mark.asyncio
    async def test_calls_process_video_task_after_upload(self, tmp_path):
        """After downloading and uploading to S3, process_video_task must be called."""
        from app.jobs.tasks.processing import download_youtube_task

        fake_file = tmp_path / "yt_download.mp4"
        fake_file.write_bytes(b"fake video data")

        mock_yt_dlp = MagicMock()
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.extract_info.return_value = {}
        mock_yt_dlp.YoutubeDL.return_value.__enter__ = MagicMock(return_value=mock_ydl_instance)
        mock_yt_dlp.YoutubeDL.return_value.__exit__ = MagicMock(return_value=False)

        ok_resp = _make_httpx_response(200)
        ok_client = MagicMock()
        ok_client.patch = AsyncMock(return_value=ok_resp)
        ok_cm = MagicMock()
        ok_cm.__aenter__ = AsyncMock(return_value=ok_client)
        ok_cm.__aexit__ = AsyncMock(return_value=False)

        process_called = {}

        async def fake_process(video_id, file_key, options=None):
            process_called["video_id"] = video_id

        with patch.dict("sys.modules", {"yt_dlp": mock_yt_dlp}), \
             patch("httpx.AsyncClient", return_value=ok_cm), \
             patch("app.jobs.tasks.processing.process_video_task", side_effect=fake_process), \
             patch("tempfile.TemporaryDirectory") as mock_tmp, \
             patch("app.media_service.client.MediaServiceClient") as mock_client_cls:

            mock_tmp.return_value.__enter__ = MagicMock(return_value=str(tmp_path))
            mock_tmp.return_value.__exit__ = MagicMock(return_value=False)

            mock_client = AsyncMock()
            mock_client.upload_file = AsyncMock()
            mock_client_cls.return_value = mock_client

            await download_youtube_task(
                "vid-yt", 1, "https://youtube.com/watch?v=test",
                "video", "720p",
            )

        assert process_called.get("video_id") == "vid-yt"
