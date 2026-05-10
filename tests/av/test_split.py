"""Tests for scripts.av.split."""

from pathlib import Path
from unittest.mock import patch

from scripts.av.split import split


def test_split_one_timestamp_produces_two_segments(tmp_path):
    timestamps = ["00:01:00"]
    expected = len(timestamps) + 1
    with patch("scripts.av.split.run_ffmpeg") as mock_ff:
        result = split(Path("video.mp4"), timestamps, tmp_path)
    assert len(result) == expected
    assert mock_ff.call_count == expected


def test_split_two_timestamps_produces_three_segments(tmp_path):
    timestamps = ["00:01:00", "00:03:00"]
    expected = len(timestamps) + 1
    with patch("scripts.av.split.run_ffmpeg") as mock_ff:
        result = split(Path("video.mp4"), timestamps, tmp_path)
    assert len(result) == expected
    assert mock_ff.call_count == expected


def test_split_names_segments_with_zero_padded_index(tmp_path):
    with patch("scripts.av.split.run_ffmpeg"):
        result = split(Path("video.mp4"), ["00:01:00"], tmp_path)
    assert result[0].name == "video_001.mp4"
    assert result[1].name == "video_002.mp4"


def test_split_first_segment_has_no_start_seek(tmp_path):
    with patch("scripts.av.split.run_ffmpeg") as mock_ff:
        split(Path("video.mp4"), ["00:01:00"], tmp_path)
    first_args = mock_ff.call_args_list[0][0][0]
    assert "-ss" not in first_args


def test_split_last_segment_has_no_end_seek(tmp_path):
    with patch("scripts.av.split.run_ffmpeg") as mock_ff:
        split(Path("video.mp4"), ["00:01:00"], tmp_path)
    last_args = mock_ff.call_args_list[-1][0][0]
    assert "-to" not in last_args


def test_split_middle_segment_has_both_ss_and_to(tmp_path):
    with patch("scripts.av.split.run_ffmpeg") as mock_ff:
        split(Path("video.mp4"), ["00:01:00", "00:03:00"], tmp_path)
    middle_args = mock_ff.call_args_list[1][0][0]
    assert "-ss" in middle_args
    assert "-to" in middle_args


def test_split_uses_stream_copy(tmp_path):
    with patch("scripts.av.split.run_ffmpeg") as mock_ff:
        split(Path("video.mp4"), ["00:01:00"], tmp_path)
    for call in mock_ff.call_args_list:
        args = call[0][0]
        assert "-c" in args
        assert args[args.index("-c") + 1] == "copy"


def test_split_creates_outputs_directory(tmp_path):
    outdir = tmp_path / "segments"
    with patch("scripts.av.split.run_ffmpeg"):
        split(Path("video.mp4"), ["00:01:00"], outdir)
    assert outdir.is_dir()
