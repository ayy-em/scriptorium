"""Tests for scripts.formats.convert_audio."""

import subprocess
from unittest.mock import patch

import pytest

from scripts.formats._utils import BatchConvertError
from scripts.formats.convert_audio import convert


def test_convert_mp4_to_mp3(tmp_path):
    src = tmp_path / "podcast.mp4"
    src.touch()
    out_dir = tmp_path / "out"
    with patch("scripts.formats.convert_audio.run_ffmpeg"):
        result = convert(src, "mp3", out_dir)
    assert len(result) == 1
    assert result[0].suffix == ".mp3"


def test_convert_lossless_target_has_no_bitrate(tmp_path):
    src = tmp_path / "song.mp3"
    src.touch()
    out_dir = tmp_path / "out"
    with patch("scripts.formats.convert_audio.run_ffmpeg") as mock_ff:
        convert(src, "wav", out_dir)
    args = mock_ff.call_args[0][0]
    assert "-b:a" not in args


def test_convert_lossy_target_uses_bitrate(tmp_path):
    src = tmp_path / "song.wav"
    src.touch()
    out_dir = tmp_path / "out"
    with patch("scripts.formats.convert_audio.run_ffmpeg") as mock_ff:
        convert(src, "mp3", out_dir)
    args = mock_ff.call_args[0][0]
    assert "-b:a" in args


def test_convert_raises_on_unknown_quality(tmp_path):
    src = tmp_path / "song.mp3"
    src.touch()
    with pytest.raises(ValueError, match="Unknown quality"):
        convert(src, "mp3", tmp_path, quality="ultra")


def test_convert_batch_processes_all_files(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    for name in ["a.mp3", "b.wav", "c.m4a"]:
        (src_dir / name).touch()
    out_dir = tmp_path / "out"
    with patch("scripts.formats.convert_audio.run_ffmpeg"):
        result = convert(src_dir, "mp3", out_dir)
    assert len(result) == 3


def test_convert_batch_continues_on_error(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    for name in ["good.mp3", "bad.mp3"]:
        (src_dir / name).touch()
    out_dir = tmp_path / "out"

    def fake_ffmpeg(args):
        if "bad.mp3" in args[args.index("-i") + 1]:
            raise subprocess.CalledProcessError(1, "ffmpeg")

    with patch("scripts.formats.convert_audio.run_ffmpeg", side_effect=fake_ffmpeg):
        with pytest.raises(BatchConvertError) as exc_info:
            convert(src_dir, "mp3", out_dir)

    assert len(exc_info.value.succeeded) == 1
