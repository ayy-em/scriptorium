"""Tests for scripts.av.convert."""

import subprocess
from unittest.mock import patch

import pytest

from scripts.av.convert import QUALITY_PRESETS, BatchConvertError, convert


def test_convert_single_video_file(tmp_path):
    src = tmp_path / "clip.avi"
    src.touch()
    out_dir = tmp_path / "out"
    with patch("scripts.av.convert.run_ffmpeg"):
        result = convert(src, "mp4", out_dir)
    assert len(result) == 1
    assert result[0].suffix == ".mp4"
    assert result[0].name == "clip.mp4"


def test_convert_creates_output_directory(tmp_path):
    src = tmp_path / "clip.avi"
    src.touch()
    out_dir = tmp_path / "out" / "nested"
    with patch("scripts.av.convert.run_ffmpeg"):
        convert(src, "mp4", out_dir)
    assert out_dir.is_dir()


def test_convert_audio_only_target_uses_bitrate_not_crf(tmp_path):
    src = tmp_path / "song.mp4"
    src.touch()
    out_dir = tmp_path / "out"
    with patch("scripts.av.convert.run_ffmpeg") as mock_ff:
        convert(src, "mp3", out_dir)
    args = mock_ff.call_args[0][0]
    assert "-crf" not in args
    assert "-b:a" in args


def test_convert_lossless_audio_target_has_no_bitrate(tmp_path):
    src = tmp_path / "song.mp3"
    src.touch()
    out_dir = tmp_path / "out"
    with patch("scripts.av.convert.run_ffmpeg") as mock_ff:
        convert(src, "wav", out_dir)
    args = mock_ff.call_args[0][0]
    assert "-b:a" not in args
    assert "-crf" not in args


def test_convert_video_target_uses_crf(tmp_path):
    src = tmp_path / "clip.avi"
    src.touch()
    out_dir = tmp_path / "out"
    with patch("scripts.av.convert.run_ffmpeg") as mock_ff:
        convert(src, "mp4", out_dir, quality="high")
    args = mock_ff.call_args[0][0]
    assert "-crf" in args
    assert args[args.index("-crf") + 1] == QUALITY_PRESETS["high"]["crf"]


def test_convert_quality_max_uses_crf_zero(tmp_path):
    src = tmp_path / "clip.avi"
    src.touch()
    out_dir = tmp_path / "out"
    with patch("scripts.av.convert.run_ffmpeg") as mock_ff:
        convert(src, "mp4", out_dir, quality="max")
    args = mock_ff.call_args[0][0]
    assert args[args.index("-crf") + 1] == "0"


def test_convert_raises_on_unknown_quality(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with pytest.raises(ValueError, match="Unknown quality"):
        convert(src, "mp4", tmp_path, quality="ultra")


def test_convert_batch_processes_all_files(tmp_path):
    file_names = ["a.mp4", "b.mp4", "c.mp4"]
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    for name in file_names:
        (src_dir / name).touch()
    out_dir = tmp_path / "out"
    with patch("scripts.av.convert.run_ffmpeg"):
        result = convert(src_dir, "mp4", out_dir)
    assert len(result) == len(file_names)


def test_convert_batch_continues_on_per_file_error(tmp_path):
    file_names = ["a.mp4", "b.mp4"]
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    for name in file_names:
        (src_dir / name).touch()
    out_dir = tmp_path / "out"

    call_count = 0

    def fake_transcode(f, o, ext, q):
        nonlocal call_count
        call_count += 1
        if f.name == "b.mp4":
            raise subprocess.CalledProcessError(1, "ffmpeg")

    with patch("scripts.av.convert._transcode", side_effect=fake_transcode):
        with pytest.raises(BatchConvertError) as exc_info:
            convert(src_dir, "mp4", out_dir)

    assert call_count == len(file_names)
    assert len(exc_info.value.succeeded) == len(file_names) - 1


def test_convert_batch_error_carries_succeeded_list(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "good.mp4").touch()
    (src_dir / "bad.mp4").touch()
    out_dir = tmp_path / "out"

    def fake_transcode(f, o, ext, q):
        if f.name == "bad.mp4":
            raise RuntimeError("encode failed")

    with patch("scripts.av.convert._transcode", side_effect=fake_transcode):
        with pytest.raises(BatchConvertError) as exc_info:
            convert(src_dir, "mp4", out_dir)

    succeeded_names = [p.name for p in exc_info.value.succeeded]
    assert "good.mp4" in succeeded_names


def test_convert_all_quality_presets_accepted(tmp_path):
    src = tmp_path / "clip.avi"
    src.touch()
    out_dir = tmp_path / "out"
    for quality in QUALITY_PRESETS:
        with patch("scripts.av.convert.run_ffmpeg"):
            result = convert(src, "mp4", out_dir, quality=quality)
        assert len(result) == 1
