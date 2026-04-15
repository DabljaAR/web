"""Unit tests for DubbingMergeService."""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock

import app.dubbing.service as dubbing_service
from app.dubbing.service import DubbingMergeService
from app.dubbing.schemas import SegmentTimingInfo


class FakeProcess:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr


class TestDubbingMergeService:
    """Unit tests for dubbing merge service."""
    
    @pytest.fixture
    def service(self):
        """Create a DubbingMergeService instance."""
        return DubbingMergeService()
    
    @pytest.fixture
    def sample_segments(self):
        """Sample segment timing info for testing."""
        return [
            SegmentTimingInfo(
                segment_id=0,
                start=0.0,
                end=5.0,
                duration=5.0,
                original_text="Hello world",
                translated_text="مرحبا بالعالم",
                tts_audio_key="tts/video-123/segment_0.wav",
                tts_duration=5.2
            ),
            SegmentTimingInfo(
                segment_id=1,
                start=6.0,
                end=10.0,
                duration=4.0,
                original_text="How are you?",
                translated_text="كيف حالك؟",
                tts_audio_key="tts/video-123/segment_1.wav",
                tts_duration=4.8
            ),
        ]
    
    @pytest.mark.asyncio
    async def test_validate_segments(self, service, sample_segments):
        """Test segment validation."""
        valid = await service._validate_segments(sample_segments)
        
        assert len(valid) == 2
        assert valid[0].segment_id == 0
        assert valid[1].segment_id == 1
        
    @pytest.mark.asyncio
    async def test_validate_segments_filters_invalid(self, service):
        """Test that invalid segments are filtered out."""
        segments = [
            SegmentTimingInfo(
                segment_id=0,
                start=0.0,
                end=5.0,
                duration=5.0,
                original_text="Valid",
                translated_text="صالح",
                tts_audio_key="tts/video-123/segment_0.wav",
            ),
            SegmentTimingInfo(
                segment_id=1,
                start=0.0,
                end=5.0,
                duration=5.0,
                original_text="Missing key",
                translated_text="مفتاح مفقود",
                tts_audio_key=None,  # Invalid - no TTS key
            ),
            SegmentTimingInfo(
                segment_id=2,
                start=10.0,
                end=5.0,  # Invalid - end before start
                duration=5.0,
                original_text="Bad timing",
                translated_text="توقيت سيء",
                tts_audio_key="tts/video-123/segment_2.wav",
            ),
        ]
        
        valid = await service._validate_segments(segments)
        
        assert len(valid) == 1
        assert valid[0].segment_id == 0
    
    @pytest.mark.asyncio
    async def test_calculate_stretch_factors(self, service, sample_segments):
        """Test stretch factor calculation."""
        # Mock segments with paths
        segments_with_paths = [
            (seg, Path(f"/tmp/segment_{seg.segment_id}.wav"))
            for seg in sample_segments
        ]
        
        stretch_info = await service._calculate_stretch_factors(segments_with_paths)
        
        assert len(stretch_info) == 2
        
        # First segment: 5.2s audio needs to fit in 5.0s = 1.04x stretch
        assert stretch_info[0]["stretch_factor"] == pytest.approx(1.04, rel=0.01)
        assert stretch_info[0]["mismatch_percent"] == pytest.approx(4.0, rel=0.1)
        
        # Second segment: 4.8s audio needs to fit in 4.0s = 1.2x stretch
        assert stretch_info[1]["stretch_factor"] == pytest.approx(1.2, rel=0.01)
        assert stretch_info[1]["mismatch_percent"] == pytest.approx(20.0, rel=0.1)
    
    @pytest.mark.asyncio
    async def test_calculate_stretch_factors_clamps_to_max(self, service):
        """Test that stretch factors are clamped to max ratio."""
        segments = [
            SegmentTimingInfo(
                segment_id=0,
                start=0.0,
                end=5.0,
                duration=5.0,
                original_text="Test",
                translated_text="اختبار",
                tts_audio_key="tts/video-123/segment_0.wav",
                tts_duration=7.0  # 40% longer - exceeds max stretch
            )
        ]
        
        segments_with_paths = [(segments[0], Path("/tmp/segment_0.wav"))]
        stretch_info = await service._calculate_stretch_factors(segments_with_paths)
        
        # Should be clamped to max stretch ratio (1.2)
        assert stretch_info[0]["stretch_factor"] == service.max_stretch
        assert stretch_info[0]["will_trim"] is True
    
    @pytest.mark.asyncio
    async def test_prepare_audio_timeline(self, service):
        """Test audio timeline preparation with gaps."""
        processed_segments = [
            {
                "segment_id": 0,
                "segment_info": SegmentTimingInfo(
                    segment_id=0,
                    start=0.0,
                    end=5.0,
                    duration=5.0,
                    original_text="First",
                    translated_text="أول",
                    tts_audio_key="tts/video-123/segment_0.wav"
                ),
                "output_path": Path("/tmp/segment_0.wav")
            },
            {
                "segment_id": 1,
                "segment_info": SegmentTimingInfo(
                    segment_id=1,
                    start=6.5,  # 1.5s gap after first segment
                    end=10.0,
                    duration=3.5,
                    original_text="Second",
                    translated_text="ثانية",
                    tts_audio_key="tts/video-123/segment_1.wav"
                ),
                "output_path": Path("/tmp/segment_1.wav")
            },
        ]
        
        timeline = await service._prepare_audio_timeline(processed_segments)
        
        assert len(timeline) == 2
        
        # First segment should have 1.5s gap after
        assert timeline[0][1] == pytest.approx(1.5, rel=0.01)
        
        # Last segment should have no gap
        assert timeline[1][1] == 0
    
    @pytest.mark.asyncio
    async def test_prepare_audio_timeline_zeroes_small_gaps(self, service):
        """Test that tiny gaps below silence threshold are removed."""
        processed_segments = [
            {
                "segment_id": 0,
                "segment_info": SegmentTimingInfo(
                    segment_id=0,
                    start=0.0,
                    end=5.0,
                    duration=5.0,
                    original_text="First",
                    translated_text="أول",
                    tts_audio_key="tts/video-123/segment_0.wav"
                ),
                "output_path": Path("/tmp/segment_0.wav")
            },
            {
                "segment_id": 1,
                "segment_info": SegmentTimingInfo(
                    segment_id=1,
                    start=5.05,  # Only 0.05s gap - below threshold
                    end=10.0,
                    duration=4.95,
                    original_text="Second",
                    translated_text="ثانية",
                    tts_audio_key="tts/video-123/segment_1.wav"
                ),
                "output_path": Path("/tmp/segment_1.wav")
            },
        ]
        
        timeline = await service._prepare_audio_timeline(processed_segments)
        
        # Gap should be removed because it's below threshold.
        assert timeline[0][1] == 0.0

    @pytest.mark.asyncio
    async def test_detect_audio_format(self, service, monkeypatch):
        """Test sample-rate/channel detection from ffprobe output."""
        async def fake_create_subprocess_exec(*cmd, **kwargs):
            return FakeProcess(returncode=0, stdout=b"24000,1\n", stderr=b"")

        monkeypatch.setattr(
            dubbing_service.asyncio,
            "create_subprocess_exec",
            fake_create_subprocess_exec,
        )

        sample_rate, channels = await service._detect_audio_format("/tmp/in.wav")
        assert sample_rate == 24000
        assert channels == 1

    @pytest.mark.asyncio
    async def test_download_tts_segments_detects_first_audio_format(self, service, tmp_path):
        """Test that first successful TTS download sets merge audio format."""
        async def fake_download(_, destination):
            Path(destination).write_bytes(b"fake-audio")
            return True

        service.storage.download = AsyncMock(side_effect=fake_download)
        service.ffmpeg.get_audio_duration = AsyncMock(return_value=1.0)
        service._detect_audio_format = AsyncMock(return_value=(24000, 1))

        segments = [
            SegmentTimingInfo(
                segment_id=0,
                start=0.0,
                end=1.0,
                duration=1.0,
                original_text="A",
                translated_text="ا",
                tts_audio_key="tts/video-123/segment_0.wav",
            )
        ]

        downloaded = await service._download_tts_segments(segments, tmp_path)
        assert len(downloaded) == 1
        assert service._tts_sample_rate == 24000
        assert service._tts_channels == 1
        service._detect_audio_format.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_silence_uses_detected_format(self, service, tmp_path, monkeypatch):
        """Silence generation must match detected TTS stream format."""
        captured = {}
        output_path = tmp_path / "silence.wav"
        service._tts_sample_rate = 24000
        service._tts_channels = 1

        async def fake_create_subprocess_exec(*cmd, **kwargs):
            captured["cmd"] = list(cmd)
            output_path.touch()
            return FakeProcess(returncode=0)

        monkeypatch.setattr(
            dubbing_service.asyncio,
            "create_subprocess_exec",
            fake_create_subprocess_exec,
        )

        ok = await service._generate_silence(output_path, 0.5)
        assert ok is True
        assert "anullsrc=r=24000:cl=mono" in captured["cmd"]

    @pytest.mark.asyncio
    async def test_apply_time_stretch_adds_afade_before_atempo(self, service, tmp_path, monkeypatch):
        """Time stretch filter should include fade-out before atempo chain."""
        captured = {}
        output_path = tmp_path / "stretched.wav"
        service.ffmpeg.get_audio_duration = AsyncMock(return_value=1.0)

        async def fake_create_subprocess_exec(*cmd, **kwargs):
            captured["cmd"] = list(cmd)
            output_path.touch()
            return FakeProcess(returncode=0)

        monkeypatch.setattr(
            dubbing_service.asyncio,
            "create_subprocess_exec",
            fake_create_subprocess_exec,
        )

        ok = await service._apply_time_stretch("input.wav", str(output_path), 1.25)
        assert ok is True

        filter_arg = captured["cmd"][captured["cmd"].index("-filter:a") + 1]
        assert filter_arg.startswith("afade=t=out:st=0.9200:d=0.0800,")
        assert "atempo=1.250" in filter_arg

    @pytest.mark.asyncio
    async def test_process_audio_segments_trims_when_will_trim(self, service, tmp_path):
        """Overflowing segments should be trimmed to target duration."""
        source_audio = tmp_path / "segment_0.wav"
        source_audio.touch()

        segment = SegmentTimingInfo(
            segment_id=0,
            start=0.0,
            end=2.0,
            duration=2.0,
            original_text="Test",
            translated_text="اختبار",
            tts_audio_key="tts/video-123/segment_0.wav",
            tts_duration=3.0,
        )
        stretch_info = [{
            "segment_id": 0,
            "segment_info": segment,
            "audio_path": source_audio,
            "target_duration": 2.0,
            "actual_duration": 3.0,
            "stretch_factor": 1.2,
            "mismatch_percent": 50.0,
            "will_trim": True,
        }]

        service._apply_time_stretch = AsyncMock(return_value=True)
        service._trim_audio = AsyncMock(return_value=True)

        processed = await service._process_audio_segments(stretch_info, tmp_path)

        assert len(processed) == 1
        assert processed[0]["output_path"].name == "segment_0_trimmed.wav"
        service._trim_audio.assert_awaited_once()
        trim_args = service._trim_audio.await_args.args
        assert trim_args[2] == pytest.approx(2.0, rel=0.001)

    @pytest.mark.asyncio
    async def test_merge_audio_segments_uses_filter_concat_and_leading_silence(
        self, service, tmp_path, monkeypatch
    ):
        """Audio merge should use filter_complex concat and honor first start offset."""
        captured = {}

        seg0 = SegmentTimingInfo(
            segment_id=0,
            start=2.0,
            end=3.0,
            duration=1.0,
            original_text="A",
            translated_text="ا",
            tts_audio_key="tts/video-123/segment_0.wav",
        )
        seg1 = SegmentTimingInfo(
            segment_id=1,
            start=3.5,
            end=4.0,
            duration=0.5,
            original_text="B",
            translated_text="ب",
            tts_audio_key="tts/video-123/segment_1.wav",
        )
        audio_0 = tmp_path / "segment_0_processed.wav"
        audio_1 = tmp_path / "segment_1_processed.wav"
        audio_0.touch()
        audio_1.touch()

        processed_segments = [
            {"segment_id": 0, "segment_info": seg0, "output_path": audio_0},
            {"segment_id": 1, "segment_info": seg1, "output_path": audio_1},
        ]

        service._prepare_audio_timeline = AsyncMock(
            return_value=[(audio_0, 0.5), (audio_1, 0.0)]
        )
        service._generate_silence = AsyncMock(return_value=True)

        async def fake_create_subprocess_exec(*cmd, **kwargs):
            captured["cmd"] = list(cmd)
            Path(cmd[-1]).touch()
            return FakeProcess(returncode=0)

        monkeypatch.setattr(
            dubbing_service.asyncio,
            "create_subprocess_exec",
            fake_create_subprocess_exec,
        )

        final_audio = await service._merge_audio_segments(processed_segments, tmp_path)

        assert final_audio.exists()
        assert service._generate_silence.await_count == 2
        leading_call = service._generate_silence.await_args_list[0].args
        assert leading_call[1] == pytest.approx(2.0, rel=0.001)

        cmd = captured["cmd"]
        assert "-filter_complex" in cmd
        assert "-c" not in cmd
        filter_arg = cmd[cmd.index("-filter_complex") + 1]
        assert "concat=n=4:v=0:a=1[out]" in filter_arg
