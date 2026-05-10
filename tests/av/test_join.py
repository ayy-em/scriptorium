"""Tests for scripts.av.join."""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.av.join import join

_VIDEO = {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080}
_AUDIO = {"codec_type": "audio", "codec_name": "aac"}


def _make_files(directory: Path, count: int, suffix: str = ".mp4") -> list[Path]:
    files = []
    for i in range(count):
        f = directory / f"clip_{i:02d}{suffix}"
        f.touch()
        files.append(f)
    return files


def test_join_raises_when_inputs_empty(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(FileNotFoundError):
        join(tmp_path, out)


def test_join_raises_when_single_file(tmp_path):
    _make_files(tmp_path, 1)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="Only one file"):
        join(tmp_path, out)


def test_join_raises_on_video_codec_mismatch(tmp_path):
    _make_files(tmp_path, 2)
    out = tmp_path / "out"
    streams_a = [{"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080}]
    streams_b = [{"codec_type": "video", "codec_name": "vp9", "width": 1920, "height": 1080}]
    with (
        patch("scripts.av.join.probe_streams", side_effect=[streams_a, streams_b]),
        pytest.raises(RuntimeError, match="incompatible"),
    ):
        join(tmp_path, out)


def test_join_raises_on_resolution_mismatch(tmp_path):
    _make_files(tmp_path, 2)
    out = tmp_path / "out"
    streams_a = [{"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080}]
    streams_b = [{"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720}]
    with (
        patch("scripts.av.join.probe_streams", side_effect=[streams_a, streams_b]),
        pytest.raises(RuntimeError, match="incompatible"),
    ):
        join(tmp_path, out)


def test_join_raises_on_audio_codec_mismatch(tmp_path):
    _make_files(tmp_path, 2)
    out = tmp_path / "out"
    streams_a = [_VIDEO, {"codec_type": "audio", "codec_name": "aac"}]
    streams_b = [_VIDEO, {"codec_type": "audio", "codec_name": "mp3"}]
    with (
        patch("scripts.av.join.probe_streams", side_effect=[streams_a, streams_b]),
        pytest.raises(RuntimeError, match="incompatible"),
    ):
        join(tmp_path, out)


def test_join_moves_inputs_to_processed(tmp_path):
    files = _make_files(tmp_path, 2)
    out = tmp_path / "out"
    streams = [[_VIDEO, _AUDIO], [_VIDEO, _AUDIO]]
    with (
        patch("scripts.av.join.probe_streams", side_effect=streams),
        patch("scripts.av.join.run_ffmpeg"),
    ):
        join(tmp_path, out)
    processed = tmp_path / "processed"
    assert processed.is_dir()
    for f in files:
        assert (processed / f.name).exists()
        assert not f.exists()


def test_join_returns_path_with_joined_in_name(tmp_path):
    _make_files(tmp_path, 2)
    out = tmp_path / "out"
    streams = [[_VIDEO, _AUDIO], [_VIDEO, _AUDIO]]
    with (
        patch("scripts.av.join.probe_streams", side_effect=streams),
        patch("scripts.av.join.run_ffmpeg"),
    ):
        result = join(tmp_path, out)
    assert "joined" in result.name
    assert result.suffix == ".mp4"
    assert result.parent == out


def test_join_passes_concat_demuxer_args_to_ffmpeg(tmp_path):
    _make_files(tmp_path, 2)
    out = tmp_path / "out"
    streams = [[_VIDEO, _AUDIO], [_VIDEO, _AUDIO]]
    with (
        patch("scripts.av.join.probe_streams", side_effect=streams),
        patch("scripts.av.join.run_ffmpeg") as mock_ff,
    ):
        join(tmp_path, out)
    args = mock_ff.call_args[0][0]
    assert "-f" in args
    assert "concat" in args
    assert "-c" in args
    assert "copy" in args
