"""Unit tests for ffmpeg mux (mocked S3 + subprocess)."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import asyncio
import pytest

from app.mux import mux_video_with_audio, replace_video_audio


def test_replace_video_audio_uses_apad_and_stream_map(tmp_path):
    video = tmp_path / "video.mp4"
    audio = tmp_path / "audio.wav"
    output = tmp_path / "out.mp4"
    video.write_bytes(b"fake-video")
    audio.write_bytes(b"fake-audio")

    captured_cmd = []

    async def fake_exec(*cmd, **kwargs):
        captured_cmd.extend(cmd)
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))
        proc.returncode = 0
        output.write_bytes(b"dubbed")
        return proc

    meta = MagicMock(duration=12.5)

    async def run():
        with patch("app.mux.get_metadata", return_value=meta), patch(
            "app.mux.asyncio.create_subprocess_exec", side_effect=fake_exec
        ):
            await replace_video_audio(video, audio, output)

    asyncio.run(run())

    cmd_str = " ".join(captured_cmd)
    assert "-filter_complex" in captured_cmd
    assert "apad=whole_dur=12.500000" in cmd_str
    assert "0:v:0" in captured_cmd
    assert "[aout]" in captured_cmd
    assert "copy" in captured_cmd
    assert "aac" in captured_cmd


def test_mux_video_with_audio_downloads_uploads(tmp_path):
    work = str(tmp_path / "work")

    async def run():
        with patch("app.mux.download_file", new_callable=AsyncMock, return_value=True), patch(
            "app.mux.replace_video_audio", new_callable=AsyncMock
        ) as replace_mock, patch("app.mux.upload_file", new_callable=AsyncMock) as upload_mock:
            result = await mux_video_with_audio(
                video_key="videos/v1/original.mp4",
                audio_key="tts/v1/combined.wav",
                output_key="dubbed/v1/dubbed_j1.mp4",
                temp_dir=work,
            )
        return result, replace_mock, upload_mock

    result, replace_mock, upload_mock = asyncio.run(run())
    assert replace_mock.await_count == 1
    upload_mock.assert_awaited_once()
    assert result["combined_audio_key"] == "tts/v1/combined.wav"
    assert result["dubbed_video_key"] == "dubbed/v1/dubbed_j1.mp4"


def test_mux_video_with_audio_download_failure():
    async def run():
        with patch("app.mux.download_file", new_callable=AsyncMock, return_value=False):
            with pytest.raises(RuntimeError, match="combined audio"):
                await mux_video_with_audio(
                    video_key="v.mp4",
                    audio_key="missing.wav",
                    output_key="out.mp4",
                    temp_dir="/tmp/test_mux",
                )

    asyncio.run(run())
