"""Tests for scripts.av._utils shared helpers."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.av._utils import (
    av_inputs_dir,
    av_outputs_dir,
    find_media_files,
    probe_streams,
    read_tags,
    run_ffmpeg,
    run_ffprobe,
)


def test_av_inputs_dir_creates_and_returns_path(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.av._utils._AV_DIR", tmp_path)
    d = av_inputs_dir()
    assert d.exists()
    assert d.name == "inputs"
    assert d.parent == tmp_path


def test_av_outputs_dir_creates_and_returns_path(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.av._utils._AV_DIR", tmp_path)
    d = av_outputs_dir()
    assert d.exists()
    assert d.name == "outputs"
    assert d.parent == tmp_path


def test_find_media_files_filters_by_extension(tmp_path):
    (tmp_path / "clip.mp4").touch()
    (tmp_path / "audio.mp3").touch()
    (tmp_path / "readme.txt").touch()
    (tmp_path / "image.jpg").touch()
    result = find_media_files(tmp_path)
    names = [f.name for f in result]
    assert "clip.mp4" in names
    assert "audio.mp3" in names
    assert "readme.txt" not in names
    assert "image.jpg" not in names


def test_find_media_files_returns_sorted(tmp_path):
    (tmp_path / "c.mp4").touch()
    (tmp_path / "a.mp4").touch()
    (tmp_path / "b.mp4").touch()
    result = find_media_files(tmp_path)
    assert [f.name for f in result] == ["a.mp4", "b.mp4", "c.mp4"]


def test_find_media_files_excludes_directories(tmp_path):
    (tmp_path / "subdir.mp4").mkdir()
    (tmp_path / "real.mp4").touch()
    result = find_media_files(tmp_path)
    assert len(result) == 1
    assert result[0].name == "real.mp4"


def test_run_ffmpeg_passes_correct_args():
    with patch("scripts.av._utils.subprocess.run") as mock_run:
        run_ffmpeg(["-i", "in.mp4", "out.mp4"])
        mock_run.assert_called_once_with(
            ["ffmpeg", "-hide_banner", "-y", "-i", "in.mp4", "out.mp4"],
            check=True,
        )


def test_run_ffprobe_parses_json_output():
    payload = {"streams": [{"codec_name": "h264"}]}
    mock_result = MagicMock()
    mock_result.stdout = json.dumps(payload)
    with patch("scripts.av._utils.subprocess.run", return_value=mock_result):
        result = run_ffprobe(["-show_streams", "video.mp4"])
    assert result == payload


def test_probe_streams_returns_stream_list():
    fake_streams = [{"codec_type": "video", "codec_name": "h264"}]
    with patch("scripts.av._utils.run_ffprobe", return_value={"streams": fake_streams}):
        result = probe_streams(Path("video.mp4"))
    assert result == fake_streams


def test_probe_streams_returns_empty_list_when_key_absent():
    with patch("scripts.av._utils.run_ffprobe", return_value={}):
        result = probe_streams(Path("video.mp4"))
    assert result == []


def test_read_tags_returns_format_tags():
    fake_data = {"format": {"tags": {"title": "My Song", "artist": "Band"}}}
    with patch("scripts.av._utils.run_ffprobe", return_value=fake_data):
        result = read_tags(Path("audio.mp3"))
    assert result == {"title": "My Song", "artist": "Band"}


def test_read_tags_returns_empty_dict_when_no_tags():
    with patch("scripts.av._utils.run_ffprobe", return_value={}):
        result = read_tags(Path("audio.mp3"))
    assert result == {}
