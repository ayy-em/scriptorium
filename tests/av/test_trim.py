"""Tests for scripts.av.trim."""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.av.trim import trim


def test_trim_with_start_and_end(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.trim.run_ffmpeg") as mock_ff:
        trim(Path("in.mp4"), out, start="00:01:00", end="00:02:00")
    mock_ff.assert_called_once_with(["-i", "in.mp4", "-ss", "00:01:00", "-to", "00:02:00", "-c", "copy", str(out)])


def test_trim_with_end_uses_default_start(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.trim.run_ffmpeg") as mock_ff:
        trim(Path("in.mp4"), out, end="00:01:00")
    args = mock_ff.call_args[0][0]
    assert "-ss" in args
    assert args[args.index("-ss") + 1] == "0"


def test_trim_with_seconds(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.trim.run_ffmpeg") as mock_ff:
        trim(Path("in.mp4"), out, seconds=30.0)
    args = mock_ff.call_args[0][0]
    assert "-t" in args
    assert args[args.index("-t") + 1] == "30.0"
    assert "-ss" not in args


def test_trim_raises_when_seconds_and_end_both_given():
    with pytest.raises(ValueError, match="mutually exclusive"):
        trim(Path("in.mp4"), Path("out.mp4"), end="00:01:00", seconds=30.0)


def test_trim_raises_when_seconds_and_start_both_given():
    with pytest.raises(ValueError, match="mutually exclusive"):
        trim(Path("in.mp4"), Path("out.mp4"), start="00:00:30", seconds=30.0)


def test_trim_raises_when_neither_end_nor_seconds():
    with pytest.raises(ValueError, match="Provide either"):
        trim(Path("in.mp4"), Path("out.mp4"))
