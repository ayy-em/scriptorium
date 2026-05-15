"""Tests for scripts.av.dump_frames."""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.av.dump_frames import dump_frames


def test_dump_frames_passes_correct_ffmpeg_args(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg") as mock_ff:
        dump_frames(Path("clip.mp4"), tmp_path, start="0m30s", end="1m0s")

    args = mock_ff.call_args[0][0]
    assert args[args.index("-ss") + 1] == "30"
    assert args[args.index("-to") + 1] == "60"
    assert args[args.index("-i") + 1] == "clip.mp4"
    assert "-vsync" in args
    assert args[args.index("-vsync") + 1] == "0"


def test_dump_frames_accepts_colon_timestamps(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg") as mock_ff:
        dump_frames(Path("clip.mp4"), tmp_path, start="01:30", end="02:00")

    args = mock_ff.call_args[0][0]
    assert args[args.index("-ss") + 1] == "01:30"
    assert args[args.index("-to") + 1] == "02:00"


def test_dump_frames_accepts_bare_seconds(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg") as mock_ff:
        dump_frames(Path("clip.mp4"), tmp_path, start="90", end="120")

    args = mock_ff.call_args[0][0]
    assert args[args.index("-ss") + 1] == "90"
    assert args[args.index("-to") + 1] == "120"


def test_dump_frames_output_dir_uses_frames_stem_label(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg"):
        dump_frames(Path("myclip.mp4"), tmp_path, start="0m10s", end="0m20s")

    expected_dir = tmp_path / "frames" / "myclip" / "0m10s-0m20s"
    assert expected_dir.exists()


def test_dump_frames_colon_label_replaces_colons_with_dots(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg"):
        dump_frames(Path("v.mp4"), tmp_path, start="01:30", end="02:00")

    expected_dir = tmp_path / "frames" / "v" / "01.30-02.00"
    assert expected_dir.exists()


def test_dump_frames_pattern_uses_frame_05d(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg") as mock_ff:
        dump_frames(Path("v.mp4"), tmp_path, start="0m0s", end="0m5s")

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
        result = dump_frames(Path("video.mp4"), tmp_path, start="0m0s", end="0m5s")

    assert [p.name for p in result] == sorted(frame_names)


def test_dump_frames_returns_empty_list_when_no_frames_written(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg"):
        result = dump_frames(Path("video.mp4"), tmp_path, start="0m0s", end="0m5s")

    assert result == []


def test_dump_frames_jpg_includes_quality_arg(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg") as mock_ff:
        dump_frames(Path("v.mp4"), tmp_path, start="0m0s", end="0m5s", fmt="jpg")

    args = mock_ff.call_args[0][0]
    assert "-q:v" in args
    assert args[args.index("-q:v") + 1] == "2"


def test_dump_frames_png_has_no_quality_arg(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg") as mock_ff:
        dump_frames(Path("v.mp4"), tmp_path, start="0m0s", end="0m5s", fmt="png")

    args = mock_ff.call_args[0][0]
    assert "-q:v" not in args
    assert "frame_%05d.png" in args[-1]


def test_dump_frames_png_returns_png_paths(tmp_path):
    frame_dir = tmp_path / "frames" / "video" / "0m0s-0m5s"
    frame_dir.mkdir(parents=True)
    for name in ["frame_00001.png", "frame_00002.png"]:
        (frame_dir / name).touch()

    with patch("scripts.av.dump_frames.run_ffmpeg"):
        result = dump_frames(Path("video.mp4"), tmp_path, start="0m0s", end="0m5s", fmt="png")

    assert all(p.suffix == ".png" for p in result)
    assert len(result) == 2


def test_dump_frames_unsupported_format_raises(tmp_path):
    with pytest.raises(ValueError, match="Unsupported format"):
        dump_frames(Path("v.mp4"), tmp_path, start="0m0s", end="0m5s", fmt="bmp")


def test_dump_frames_no_start_omits_ss(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg") as mock_ff:
        dump_frames(Path("v.mp4"), tmp_path, end="0m5s")

    args = mock_ff.call_args[0][0]
    assert "-ss" not in args
    assert args[args.index("-to") + 1] == "5"


def test_dump_frames_no_end_omits_to(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg") as mock_ff:
        dump_frames(Path("v.mp4"), tmp_path, start="0m10s")

    args = mock_ff.call_args[0][0]
    assert "-to" not in args
    assert args[args.index("-ss") + 1] == "10"


def test_dump_frames_no_start_no_end_dumps_entire_video(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg") as mock_ff:
        dump_frames(Path("v.mp4"), tmp_path)

    args = mock_ff.call_args[0][0]
    assert "-ss" not in args
    assert "-to" not in args


def test_dump_frames_no_timestamps_label(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg"):
        dump_frames(Path("clip.mp4"), tmp_path)

    expected_dir = tmp_path / "frames" / "clip" / "0-end"
    assert expected_dir.exists()


def test_dump_frames_start_only_label(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg"):
        dump_frames(Path("clip.mp4"), tmp_path, start="01:30")

    expected_dir = tmp_path / "frames" / "clip" / "01.30-end"
    assert expected_dir.exists()


def test_dump_frames_end_only_label(tmp_path):
    with patch("scripts.av.dump_frames.run_ffmpeg"):
        dump_frames(Path("clip.mp4"), tmp_path, end="02:00")

    expected_dir = tmp_path / "frames" / "clip" / "0-02.00"
    assert expected_dir.exists()
