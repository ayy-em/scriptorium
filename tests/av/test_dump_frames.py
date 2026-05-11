"""Tests for scripts.av.dump_frames."""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.av.dump_frames import dump_frames, parse_timestamp

# --- parse_timestamp ---


def test_parse_timestamp_valid_minutes_and_seconds():
    mins, secs = 1, 30
    assert parse_timestamp(f"{mins}m{secs}s") == mins * 60 + secs


def test_parse_timestamp_zero_minutes():
    mins, secs = 0, 45
    assert parse_timestamp(f"{mins}m{secs}s") == mins * 60 + secs


def test_parse_timestamp_zero_seconds():
    mins, secs = 2, 0
    assert parse_timestamp(f"{mins}m{secs}s") == mins * 60 + secs


def test_parse_timestamp_large_values():
    mins, secs = 10, 59
    assert parse_timestamp(f"{mins}m{secs}s") == mins * 60 + secs


def test_parse_timestamp_invalid_format_raises():
    with pytest.raises(ValueError, match="Invalid timestamp"):
        parse_timestamp("90s")


def test_parse_timestamp_plain_seconds_raises():
    with pytest.raises(ValueError, match="Invalid timestamp"):
        parse_timestamp("120")


def test_parse_timestamp_wrong_separator_raises():
    with pytest.raises(ValueError, match="Invalid timestamp"):
        parse_timestamp("1:30")


# --- dump_frames ---


def test_dump_frames_raises_when_start_equals_end(tmp_path):
    with pytest.raises(ValueError, match="must be before"):
        dump_frames(Path("video.mp4"), "1m0s", "1m0s", tmp_path)


def test_dump_frames_raises_when_start_after_end(tmp_path):
    with pytest.raises(ValueError, match="must be before"):
        dump_frames(Path("video.mp4"), "2m0s", "1m0s", tmp_path)


def test_dump_frames_passes_correct_ffmpeg_args(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg") as mock_ff:
        dump_frames(Path("clip.mp4"), "0m30s", "1m0s", tmp_path)

    args = mock_ff.call_args[0][0]
    assert args[args.index("-ss") + 1] == "30.0"
    assert args[args.index("-to") + 1] == "60.0"
    assert args[args.index("-i") + 1] == "clip.mp4"
    assert "-vsync" in args
    assert args[args.index("-vsync") + 1] == "0"


def test_dump_frames_output_dir_is_frames_stem_start_end(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg"):
        dump_frames(Path("myclip.mp4"), "0m10s", "0m20s", tmp_path)

    expected_dir = tmp_path / "frames" / "myclip" / "0m10s-0m20s"
    assert expected_dir.exists()


def test_dump_frames_pattern_uses_frame_05d(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg") as mock_ff:
        dump_frames(Path("v.mp4"), "0m0s", "0m5s", tmp_path)

    args = mock_ff.call_args[0][0]
    pattern_arg = args[-1]
    assert "frame_%05d.jpg" in pattern_arg


def test_dump_frames_returns_sorted_jpg_paths(tmp_path):
    frame_dir = tmp_path / "frames" / "video" / "0m0s-0m5s"
    frame_dir.mkdir(parents=True)
    frame_names = ["frame_00003.jpg", "frame_00001.jpg", "frame_00002.jpg"]
    for name in frame_names:
        (frame_dir / name).touch()

    with patch("scripts.av.dump_frames.run_ffmpeg"):
        result = dump_frames(Path("video.mp4"), "0m0s", "0m5s", tmp_path)

    assert [p.name for p in result] == sorted(frame_names)


def test_dump_frames_returns_empty_list_when_no_frames_written(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg"):
        result = dump_frames(Path("video.mp4"), "0m0s", "0m5s", tmp_path)

    assert result == []
