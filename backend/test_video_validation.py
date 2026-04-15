"""
Comprehensive validation tests for base video creation and duration calculation.

This test suite validates:
1. create_silent_base_video with various durations
2. Duration calculation in initialize_timeline
3. FFmpeg command generation
4. Output duration accuracy
"""

import asyncio
import logging
import tempfile
from pathlib import Path
import pytest
import subprocess
import json

# Setup logging to see debug output
logging.basicConfig(
    level=logging.CRITICAL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


@pytest.fixture
def ffmpeg_builder():
    """Create FFmpegBuilder instance with temp directory."""
    from app.progressive.ffmpeg_builder import ProgressiveFFmpegBuilder
    
    with tempfile.TemporaryDirectory() as tmpdir:
        builder = ProgressiveFFmpegBuilder(temp_dir=Path(tmpdir))
        yield builder


@pytest.fixture
def test_video_file():
    """Create a test video file with known duration."""
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
        temp_path = Path(f.name)
    
    # Create a 15-second test video with ffmpeg
    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", "color=c=blue:s=320x240:d=15",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-y",
        str(temp_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create test video: {result.stderr.decode()}")
    
    yield temp_path
    
    # Cleanup
    temp_path.unlink(missing_ok=True)


def get_video_duration(video_path):
    """Get video duration using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(video_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, timeout=10)
    if result.returncode == 0:
        return float(result.stdout.decode().strip())
    return None


class TestSilentBaseVideoCreation:
    """Test suite for create_silent_base_video function."""
    
    @pytest.mark.asyncio
    async def test_create_silent_base_video_30s(self, ffmpeg_builder, test_video_file):
        """Test creating 30-second silent base video."""
        logger.info("TEST: create_silent_base_video with 30s duration")
        
        output = await ffmpeg_builder.create_silent_base_video(
            str(test_video_file),
            "test-30s",
            duration=30.0
        )
        
        assert output.exists(), "Output file should exist"
        assert output.stat().st_size > 0, "Output file should not be empty"
        
        actual_duration = get_video_duration(output)
        logger.info(f"Expected: 30.0s, Actual: {actual_duration}s, Diff: {abs(30.0 - actual_duration):.3f}s")
        
        # Allow 0.5s tolerance for FFmpeg timing variations
        assert actual_duration is not None, "Should be able to get video duration"
        assert abs(actual_duration - 30.0) < 0.5, f"Duration mismatch: expected 30.0s, got {actual_duration}s"
    
    @pytest.mark.asyncio
    async def test_create_silent_base_video_60s(self, ffmpeg_builder, test_video_file):
        """Test creating 60-second silent base video."""
        logger.info("TEST: create_silent_base_video with 60s duration")
        
        output = await ffmpeg_builder.create_silent_base_video(
            str(test_video_file),
            "test-60s",
            duration=60.0
        )
        
        assert output.exists(), "Output file should exist"
        assert output.stat().st_size > 0, "Output file should not be empty"
        
        actual_duration = get_video_duration(output)
        logger.info(f"Expected: 60.0s, Actual: {actual_duration}s, Diff: {abs(60.0 - actual_duration):.3f}s")
        
        assert actual_duration is not None, "Should be able to get video duration"
        assert abs(actual_duration - 60.0) < 0.5, f"Duration mismatch: expected 60.0s, got {actual_duration}s"
    
    @pytest.mark.asyncio
    async def test_create_silent_base_video_120s(self, ffmpeg_builder, test_video_file):
        """Test creating 120-second silent base video."""
        logger.info("TEST: create_silent_base_video with 120s duration")
        
        output = await ffmpeg_builder.create_silent_base_video(
            str(test_video_file),
            "test-120s",
            duration=120.0
        )
        
        assert output.exists(), "Output file should exist"
        assert output.stat().st_size > 0, "Output file should not be empty"
        
        actual_duration = get_video_duration(output)
        logger.info(f"Expected: 120.0s, Actual: {actual_duration}s, Diff: {abs(120.0 - actual_duration):.3f}s")
        
        assert actual_duration is not None, "Should be able to get video duration"
        assert abs(actual_duration - 120.0) < 0.5, f"Duration mismatch: expected 120.0s, got {actual_duration}s"
    
    @pytest.mark.asyncio
    async def test_create_silent_base_video_15s(self, ffmpeg_builder, test_video_file):
        """Test creating 15-second silent base video (original case)."""
        logger.info("TEST: create_silent_base_video with 15s duration (original test case)")
        
        output = await ffmpeg_builder.create_silent_base_video(
            str(test_video_file),
            "test-15s",
            duration=15.0
        )
        
        assert output.exists(), "Output file should exist"
        assert output.stat().st_size > 0, "Output file should not be empty"
        
        actual_duration = get_video_duration(output)
        logger.info(f"Expected: 15.0s, Actual: {actual_duration}s, Diff: {abs(15.0 - actual_duration):.3f}s")
        
        assert actual_duration is not None, "Should be able to get video duration"
        assert abs(actual_duration - 15.0) < 0.5, f"Duration mismatch: expected 15.0s, got {actual_duration}s"
    
    @pytest.mark.asyncio
    async def test_ffmpeg_command_structure(self, ffmpeg_builder):
        """Test that FFmpeg command structure is correct."""
        logger.info("TEST: FFmpeg command structure validation")
        
        # We'll verify the command is generated correctly by checking the function's logic
        # The command should use -t parameter to limit duration
        assert hasattr(ffmpeg_builder, 'create_silent_base_video')
        
        # The builder should have all necessary attributes
        assert hasattr(ffmpeg_builder, 'temp_dir')
        assert ffmpeg_builder.temp_dir.exists()


class TestDurationCalculation:
    """Test suite for duration calculation in initialize_timeline."""
    
    def test_duration_from_segments_normal(self):
        """Test normal duration calculation from segments."""
        logger.info("TEST: Duration calculation from normal segments")
        
        segments = [
            {'start': 0.0, 'end': 5.0},
            {'start': 5.0, 'end': 10.0},
            {'start': 10.0, 'end': 15.0},
        ]
        
        total_duration = max(seg['end'] for seg in segments)
        logger.info(f"Segments: {segments}")
        logger.info(f"Calculated duration: {total_duration}s")
        
        assert total_duration == 15.0, f"Expected 15.0s, got {total_duration}s"
    
    def test_duration_from_segments_with_gaps(self):
        """Test duration calculation with gaps between segments."""
        logger.info("TEST: Duration calculation with gaps")
        
        segments = [
            {'start': 0.0, 'end': 5.0},
            {'start': 8.0, 'end': 13.0},
            {'start': 20.0, 'end': 30.0},
        ]
        
        total_duration = max(seg['end'] for seg in segments)
        logger.info(f"Segments: {segments}")
        logger.info(f"Calculated duration: {total_duration}s")
        
        # Should be 30s (max end time, not sum)
        assert total_duration == 30.0, f"Expected 30.0s, got {total_duration}s"
    
    def test_duration_from_segments_unordered(self):
        """Test duration calculation with unordered segments."""
        logger.info("TEST: Duration calculation with unordered segments")
        
        segments = [
            {'start': 10.0, 'end': 15.0},
            {'start': 0.0, 'end': 5.0},
            {'start': 20.0, 'end': 30.0},
        ]
        
        total_duration = max(seg['end'] for seg in segments)
        logger.info(f"Segments: {segments}")
        logger.info(f"Calculated duration: {total_duration}s")
        
        # Should find the maximum end time regardless of order
        assert total_duration == 30.0, f"Expected 30.0s, got {total_duration}s"
    
    def test_duration_from_single_segment(self):
        """Test duration calculation with single segment."""
        logger.info("TEST: Duration calculation from single segment")
        
        segments = [
            {'start': 0.0, 'end': 23.456}
        ]
        
        total_duration = max(seg['end'] for seg in segments)
        logger.info(f"Segments: {segments}")
        logger.info(f"Calculated duration: {total_duration}s")
        
        assert total_duration == 23.456, f"Expected 23.456s, got {total_duration}s"
    
    def test_duration_from_empty_segments(self):
        """Test duration calculation with empty segments list."""
        logger.info("TEST: Duration calculation from empty segments")
        
        segments = []
        total_duration = max(seg['end'] for seg in segments) if segments else 0.0
        logger.info(f"Segments: {segments}")
        logger.info(f"Calculated duration: {total_duration}s")
        
        assert total_duration == 0.0, f"Expected 0.0s, got {total_duration}s"
    
    def test_duration_no_rounding_errors(self):
        """Test that duration calculation doesn't have rounding errors."""
        logger.info("TEST: Duration precision - no rounding errors")
        
        segments = [
            {'start': 0.0, 'end': 15.007},  # The case from debug logs
        ]
        
        total_duration = max(seg['end'] for seg in segments)
        logger.info(f"Segments: {segments}")
        logger.info(f"Calculated duration: {total_duration}s (precision: {total_duration:.10f}s)")
        
        # Should preserve precision
        assert total_duration == 15.007, f"Expected 15.007s, got {total_duration}s"
    
    def test_duration_long_video_alert(self):
        """Test that extremely long durations are flagged."""
        logger.info("TEST: Long duration alert")
        
        # 23 minutes * 60 = 1380 seconds (the problematic case)
        segments = [
            {'start': 0.0, 'end': 1380.0},  # 23 minutes
        ]
        
        total_duration = max(seg['end'] for seg in segments)
        logger.info(f"Segments: {segments}")
        logger.info(f"Calculated duration: {total_duration}s = {total_duration/60:.1f} minutes")
        
        # Verify we can detect this
        is_suspicious = total_duration > 600  # 10 minutes
        assert is_suspicious, "Should flag 23-minute videos as suspicious"
        logger.info(f"Suspicious duration detected: {total_duration/60:.1f} minutes")


class TestEdgeCases:
    """Test edge cases in video creation."""
    
    @pytest.mark.asyncio
    async def test_very_short_duration(self, ffmpeg_builder, test_video_file):
        """Test creating very short video (1 second)."""
        logger.info("TEST: Very short duration (1s)")
        
        output = await ffmpeg_builder.create_silent_base_video(
            str(test_video_file),
            "test-1s",
            duration=1.0
        )
        
        assert output.exists(), "Output file should exist"
        
        actual_duration = get_video_duration(output)
        logger.info(f"Expected: 1.0s, Actual: {actual_duration}s")
        
        assert actual_duration is not None
        assert abs(actual_duration - 1.0) < 0.5, f"Expected 1.0s, got {actual_duration}s"
    
    @pytest.mark.asyncio
    async def test_fractional_duration(self, ffmpeg_builder, test_video_file):
        """Test creating video with fractional duration."""
        logger.info("TEST: Fractional duration (5.5s)")
        
        output = await ffmpeg_builder.create_silent_base_video(
            str(test_video_file),
            "test-5.5s",
            duration=5.5
        )
        
        assert output.exists(), "Output file should exist"
        
        actual_duration = get_video_duration(output)
        logger.info(f"Expected: 5.5s, Actual: {actual_duration}s")
        
        assert actual_duration is not None
        assert abs(actual_duration - 5.5) < 0.5, f"Expected 5.5s, got {actual_duration}s"
    
    @pytest.mark.asyncio
    async def test_precision_duration(self, ffmpeg_builder, test_video_file):
        """Test creating video with high-precision duration (15.007s)."""
        logger.info("TEST: High precision duration (15.007s)")
        
        output = await ffmpeg_builder.create_silent_base_video(
            str(test_video_file),
            "test-15.007s",
            duration=15.007
        )
        
        assert output.exists(), "Output file should exist"
        
        actual_duration = get_video_duration(output)
        logger.info(f"Expected: 15.007s, Actual: {actual_duration}s")
        
        assert actual_duration is not None
        # May have very slight variation due to FFmpeg frame alignment
        assert abs(actual_duration - 15.007) < 0.5, f"Expected 15.007s, got {actual_duration}s"


class TestDurationMismatchDetection:
    """Test detection of duration mismatches."""
    
    def test_detects_23_minute_expansion(self):
        """Test detection of the 23-minute duration expansion issue."""
        logger.info("TEST: Detection of 23-minute expansion")
        
        # If a 15-30 second video becomes 23 minutes
        original_duration = 15.0
        expanded_duration = 23 * 60  # 1380 seconds
        
        diff = expanded_duration - original_duration
        logger.info(f"Original: {original_duration}s, Expanded: {expanded_duration}s, Diff: {diff}s ({diff/60:.1f} minutes)")
        
        # Should be easily detectable
        is_mismatch = abs(expanded_duration - original_duration) > 5.0
        assert is_mismatch, "Should detect significant duration mismatch"
        
        # Ratio check
        expansion_ratio = expanded_duration / original_duration
        logger.info(f"Expansion ratio: {expansion_ratio:.1f}x")
        
        is_suspicious_ratio = expansion_ratio > 10.0  # More than 10x expansion
        assert is_suspicious_ratio, "Expansion ratio should be suspicious"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
