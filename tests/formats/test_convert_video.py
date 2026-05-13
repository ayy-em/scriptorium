"""Tests for scripts.formats.convert_video."""

import subprocess
from unittest.mock import patch

import pytest

from scripts.formats._utils import QUALITY_PRESETS, BatchConvertError
from scripts.formats.convert_video import convert


def test_convert_single_file(tmp_path):
    src = tmp_path / "clip.avi"
    src.touch()
    out_dir = tmp_path / "out"
    with patch("scripts.formats.convert_video.run_ffmpeg"):
        result = convert(src, "mp4", out_dir)
    assert len(result) == 1
    assert result[0].suffix == ".mp4"
    assert result[0].name == "clip.mp4"


def test_convert_creates_output_directory(tmp_path):
    src = tmp_path / "clip.avi"
    src.touch()
    out_dir = tmp_path / "out" / "nested"
    with patch("scripts.formats.convert_video.run_ffmpeg"):
        convert(src, "mp4", out_dir)
    assert out_dir.is_dir()


def test_convert_uses_crf(tmp_path):
    src = tmp_path / "clip.avi"
    src.touch()
    out_dir = tmp_path / "out"
    with patch("scripts.formats.convert_video.run_ffmpeg") as mock_ff:
        convert(src, "mp4", out_dir, quality="high")
    args = mock_ff.call_args[0][0]
    assert "-crf" in args
    assert args[args.index("-crf") + 1] == QUALITY_PRESETS["high"]["crf"]


def test_convert_quality_max_uses_crf_zero(tmp_path):
    src = tmp_path / "clip.avi"
    src.touch()
    out_dir = tmp_path / "out"
    with patch("scripts.formats.convert_video.run_ffmpeg") as mock_ff:
        convert(src, "mp4", out_dir, quality="max")
    args = mock_ff.call_args[0][0]
    assert args[args.index("-crf") + 1] == "0"


def test_convert_no_audio_adds_an_flag(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    out_dir = tmp_path / "out"
    with patch("scripts.formats.convert_video.run_ffmpeg") as mock_ff:
        convert(src, "mkv", out_dir, no_audio=True)
    args = mock_ff.call_args[0][0]
    assert "-an" in args


def test_convert_raises_on_unknown_quality(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with pytest.raises(ValueError, match="Unknown quality"):
        convert(src, "mp4", tmp_path, quality="ultra")


def test_convert_batch_processes_all_files(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    for name in ["a.mp4", "b.mp4", "c.avi"]:
        (src_dir / name).touch()
    out_dir = tmp_path / "out"
    with patch("scripts.formats.convert_video.run_ffmpeg"):
        result = convert(src_dir, "mp4", out_dir)
    assert len(result) == 3


def test_convert_batch_continues_on_per_file_error(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    for name in ["a.mp4", "b.mp4"]:
        (src_dir / name).touch()
    out_dir = tmp_path / "out"

    call_count = 0

    def fake_ffmpeg(args):
        nonlocal call_count
        call_count += 1
        if "b.mp4" in args[args.index("-i") + 1]:
            raise subprocess.CalledProcessError(1, "ffmpeg")

    with patch("scripts.formats.convert_video.run_ffmpeg", side_effect=fake_ffmpeg):
        with pytest.raises(BatchConvertError) as exc_info:
            convert(src_dir, "mp4", out_dir)

    assert call_count == 2
    assert len(exc_info.value.succeeded) == 1
