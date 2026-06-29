"""Unit tests for audio_combine stretch factor math."""
from app.audio_combine import calculate_stretch_factor


def test_calculate_stretch_factor_identity():
    assert calculate_stretch_factor(2.0, 2.0) == 1.0


def test_calculate_stretch_factor_clamped_high():
    # actual/target = 3.0, max=1.2
    assert calculate_stretch_factor(1.0, 3.0, max_stretch=1.2) == 1.2


def test_calculate_stretch_factor_clamped_low():
    # actual/target = 0.3, min=0.8
    assert calculate_stretch_factor(1.0, 0.3, min_stretch=0.8) == 0.8


def test_calculate_stretch_factor_zero_target():
    assert calculate_stretch_factor(0.0, 1.0) == 1.0


def test_prepare_audio_timeline_gap():
    from pathlib import Path

    from app.audio_combine import SegmentInfo, prepare_audio_timeline

    processed = [
        {
            "segment_info": SegmentInfo(segment_id=0, start=0.0, end=2.0),
            "output_path": Path("/tmp/a.wav"),
        },
        {
            "segment_info": SegmentInfo(segment_id=1, start=3.0, end=5.0),
            "output_path": Path("/tmp/b.wav"),
        },
    ]
    timeline = prepare_audio_timeline(processed, silence_threshold=0.1)
    assert len(timeline) == 2
    assert timeline[0][1] == 1.0  # gap between end=2 and start=3
    assert timeline[1][1] == 0.0
