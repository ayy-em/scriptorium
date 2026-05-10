"""Tests for scripts.av.extract_frames."""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.av.extract_frames import extract_frames


def test_extract_frames_raises_when_count_is_zero(tmp_path):
    with pytest.raises(ValueError, match="count must be"):
        extract_frames(Path("video.mp4"), 0, tmp_path)


def test_extract_frames_raises_when_count_is_negative(tmp_path):
    with pytest.raises(ValueError, match="count must be"):
        extract_frames(Path("video.mp4"), -1, tmp_path)


def test_extract_frames_count_one_uses_midpoint(tmp_path):
    with (
        patch("scripts.av.extract_frames.run_ffmpeg") as mock_ff,
        patch("scripts.av.extract_frames._get_video_duration", return_value=100.0),
    ):
        result = extract_frames(Path("video.mp4"), 1, tmp_path)
    assert len(result) == 1
    args = mock_ff.call_args[0][0]
    assert args[args.index("-ss") + 1] == "50.000"


def test_extract_frames_count_three_uses_evenly_spaced_seeks(tmp_path):
    count = 3
    with (
        patch("scripts.av.extract_frames.run_ffmpeg") as mock_ff,
        patch("scripts.av.extract_frames._get_video_duration", return_value=100.0),
    ):
        result = extract_frames(Path("video.mp4"), count, tmp_path)
    assert len(result) == count
    all_args = [call[0][0] for call in mock_ff.call_args_list]
    seeks = [args[args.index("-ss") + 1] for args in all_args]
    assert seeks == ["25.000", "50.000", "75.000"]


def test_extract_frames_names_output_files_sequentially(tmp_path):
    with (
        patch("scripts.av.extract_frames.run_ffmpeg"),
        patch("scripts.av.extract_frames._get_video_duration", return_value=10.0),
    ):
        result = extract_frames(Path("myvideo.mp4"), 2, tmp_path)
    assert result[0].name == "frame_001.jpg"
    assert result[1].name == "frame_002.jpg"


def test_extract_frames_places_output_in_frames_stem_subdir(tmp_path):
    with (
        patch("scripts.av.extract_frames.run_ffmpeg"),
        patch("scripts.av.extract_frames._get_video_duration", return_value=10.0),
    ):
        result = extract_frames(Path("myvideo.mp4"), 1, tmp_path)
    assert result[0].parent.name == "myvideo"
    assert result[0].parent.parent.name == "frames"


def test_extract_frames_directory_processes_each_video(tmp_path):
    video_files = ["a.mp4", "b.mp4"]
    src_dir = tmp_path / "videos"
    src_dir.mkdir()
    for name in video_files:
        (src_dir / name).touch()
    out_dir = tmp_path / "out"
    with (
        patch("scripts.av.extract_frames.run_ffmpeg"),
        patch("scripts.av.extract_frames._get_video_duration", return_value=10.0),
    ):
        result = extract_frames(src_dir, 1, out_dir)
    assert len(result) == len(video_files)


def test_extract_frames_directory_raises_when_no_videos(tmp_path):
    src_dir = tmp_path / "empty"
    src_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        extract_frames(src_dir, 1, tmp_path)


def test_extract_frames_directory_skips_non_video_files(tmp_path):
    src_dir = tmp_path / "mixed"
    src_dir.mkdir()
    (src_dir / "video.mp4").touch()
    (src_dir / "audio.mp3").touch()
    (src_dir / "image.jpg").touch()
    out_dir = tmp_path / "out"
    with (
        patch("scripts.av.extract_frames.run_ffmpeg"),
        patch("scripts.av.extract_frames._get_video_duration", return_value=10.0),
    ):
        result = extract_frames(src_dir, 1, out_dir)
    assert len(result) == 1
