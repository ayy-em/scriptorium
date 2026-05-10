"""Tests for scripts.av.tag."""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.av.tag import get_tags, write_tags


def test_get_tags_returns_tag_dict():
    with patch("scripts.av.tag.read_tags", return_value={"title": "Song", "artist": "Band"}):
        result = get_tags(Path("audio.mp3"))
    assert result == {"title": "Song", "artist": "Band"}


def test_write_tags_includes_metadata_args(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.tag.run_ffmpeg") as mock_ff:
        write_tags(Path("in.mp4"), out, title="My Title", artist="Me")
    args = mock_ff.call_args[0][0]
    assert "-metadata" in args
    assert "title=My Title" in args
    assert "artist=Me" in args


def test_write_tags_uses_stream_copy(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.tag.run_ffmpeg") as mock_ff:
        write_tags(Path("in.mp4"), out, title="T")
    args = mock_ff.call_args[0][0]
    assert "-codec" in args
    assert args[args.index("-codec") + 1] == "copy"


def test_write_tags_raises_when_nothing_provided():
    with pytest.raises(ValueError, match="No tags or cover"):
        write_tags(Path("in.mp4"), Path("out.mp4"))


def test_write_tags_raises_for_unsupported_cover_format():
    with pytest.raises(ValueError, match="not supported"):
        write_tags(Path("in.avi"), Path("out.avi"), cover=Path("cover.jpg"))


def test_write_tags_allows_unsupported_format_with_force(tmp_path):
    out = tmp_path / "out.avi"
    with patch("scripts.av.tag.run_ffmpeg"):
        write_tags(Path("in.avi"), out, cover=Path("cover.jpg"), force=True)


def test_write_tags_cover_adds_map_and_disposition_args(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.tag.run_ffmpeg") as mock_ff:
        write_tags(Path("in.mp4"), out, cover=Path("cover.jpg"), title="T")
    args = mock_ff.call_args[0][0]
    assert "-map" in args
    assert "-disposition:v:1" in args
    assert "attached_pic" in args


def test_write_tags_cover_adds_cover_input(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.tag.run_ffmpeg") as mock_ff:
        write_tags(Path("in.mp4"), out, cover=Path("cover.jpg"), title="T")
    args = mock_ff.call_args[0][0]
    inputs = [args[i + 1] for i, a in enumerate(args) if a == "-i"]
    assert "in.mp4" in inputs
    assert "cover.jpg" in inputs


def test_write_tags_without_cover_has_single_input(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.tag.run_ffmpeg") as mock_ff:
        write_tags(Path("in.mp4"), out, title="T")
    args = mock_ff.call_args[0][0]
    inputs = [args[i + 1] for i, a in enumerate(args) if a == "-i"]
    assert inputs == ["in.mp4"]
