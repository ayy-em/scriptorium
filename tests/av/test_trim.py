"""Tests for scripts.av.trim.

These assert input-side seeking: ``-ss`` before ``-i`` so ffmpeg starts from the
nearest keyframe, and ``-t <duration>`` rather than ``-to <absolute>`` to match
input-side semantics. See commit d891096.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.av.trim import trim


@pytest.fixture(autouse=True)
def _stub_duration_probe():
    """Keep progress reporting from probing media files that do not exist."""
    with patch("scripts.av.trim.probe_duration_or_none", return_value=None):
        yield


def test_trim_with_start_and_end(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.trim.run_ffmpeg_with_progress") as mock_ff:
        trim(Path("in.mp4"), out, start="00:01:00", end="00:02:00")
    mock_ff.assert_called_once()
    assert mock_ff.call_args[0][0] == (
        [
            "-ss",
            "00:01:00",
            "-i",
            "in.mp4",
            "-t",
            "00:01:00.000",
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            str(out),
        ]
    )


def test_trim_seeks_on_the_input_side(tmp_path):
    """-ss must precede -i, otherwise ffmpeg decodes and discards everything before the cut."""
    out = tmp_path / "out.mp4"
    with patch("scripts.av.trim.run_ffmpeg_with_progress") as mock_ff:
        trim(Path("in.mp4"), out, start="00:01:00", end="00:02:00")
    args = mock_ff.call_args[0][0]
    assert args.index("-ss") < args.index("-i")


def test_trim_without_end_omits_duration(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.trim.run_ffmpeg_with_progress") as mock_ff:
        trim(Path("in.mp4"), out, start="00:03")
    args = mock_ff.call_args[0][0]
    assert args[args.index("-ss") + 1] == "00:03"
    assert "-t" not in args
    assert "-to" not in args


def test_trim_accepts_mm_ss_format(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.trim.run_ffmpeg_with_progress") as mock_ff:
        trim(Path("in.mp4"), out, start="1:03", end="5:04")
    args = mock_ff.call_args[0][0]
    assert args[args.index("-ss") + 1] == "1:03"
    # 5:04 - 1:03 = 4m01s, passed as a duration rather than an absolute end.
    assert args[args.index("-t") + 1] == "00:04:01.000"


def test_trim_avoids_negative_timestamps(tmp_path):
    """Input-side seeking can leave a negative start PTS, which breaks stream copy."""
    out = tmp_path / "out.mp4"
    with patch("scripts.av.trim.run_ffmpeg_with_progress") as mock_ff:
        trim(Path("in.mp4"), out, start="00:01:00")
    args = mock_ff.call_args[0][0]
    assert args[args.index("-avoid_negative_ts") + 1] == "make_zero"


def test_trim_uses_stream_copy(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.trim.run_ffmpeg_with_progress") as mock_ff:
        trim(Path("in.mp4"), out, start="00:01:00")
    args = mock_ff.call_args[0][0]
    assert args[args.index("-c") + 1] == "copy"
