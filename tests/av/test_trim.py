"""Tests for scripts.av.trim.

Two things are asserted here. Input-side seeking: ``-ss`` before ``-i`` so
ffmpeg starts from the nearest keyframe, and ``-t <duration>`` rather than
``-to <absolute>`` to match input-side semantics (see commit d891096). And the
accuracy decision: a stream copy begins at a keyframe, so when the nearest one
is not where the user asked, the cut is re-encoded instead of silently rounded.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.av.trim import MODE_FAST, MODE_PRECISE, trim


@pytest.fixture(autouse=True)
def _stub_duration_probe():
    """Keep progress reporting from probing media files that do not exist."""
    with patch("scripts.av.trim.probe_duration_or_none", return_value=None):
        yield


@pytest.fixture(autouse=True)
def _keyframe_lands_on_the_cut():
    """Default every test to a source whose keyframes suit the requested cut.

    The copy path is what most of these tests are about, so the probe is stubbed
    rather than left to fail open against files that do not exist.
    """
    with patch("scripts.av.trim.copy_would_land_on", return_value=(True, 0.0)) as probe:
        yield probe


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


def _ffmpeg_args(mock_ff):
    """Return the argument list the trim handed to ffmpeg."""
    return mock_ff.call_args[0][0]


class TestKeyframeAccuracy:
    """A cut the user asked for must be the cut they get."""

    def test_reencodes_when_the_nearest_keyframe_is_too_far_back(self, tmp_path):
        """The original bug: a sparsely-keyed source returned ~the whole file."""
        out = tmp_path / "out.mp4"
        with (
            patch("scripts.av.trim.copy_would_land_on", return_value=(False, 0.0)),
            patch("scripts.av.trim.has_video_stream", return_value=True),
            patch("scripts.av.trim.run_ffmpeg_with_progress") as mock_ff,
        ):
            strategy = trim(Path("in.mp4"), out, start="00:01")
        args = _ffmpeg_args(mock_ff)
        assert strategy == "reencode"
        assert "-c" not in args, "a re-encode must not stream-copy the video"
        assert args[args.index("-c:a") + 1] == "copy"
        assert "-crf" in args

    def test_copies_when_a_keyframe_lands_on_the_cut(self, tmp_path):
        out = tmp_path / "out.mp4"
        with patch("scripts.av.trim.run_ffmpeg_with_progress") as mock_ff:
            strategy = trim(Path("in.mp4"), out, start="00:01")
        assert strategy == "copy"
        assert _ffmpeg_args(mock_ff)[-4:-1] == ["copy", "-avoid_negative_ts", "make_zero"]

    def test_fast_mode_never_probes_and_never_reencodes(self, tmp_path, _keyframe_lands_on_the_cut):
        """--fast is the opt-out: accept the keyframe snap, skip the probe entirely."""
        out = tmp_path / "out.mp4"
        with patch("scripts.av.trim.run_ffmpeg_with_progress") as mock_ff:
            strategy = trim(Path("in.mp4"), out, start="00:01", mode=MODE_FAST)
        assert strategy == "copy"
        assert _keyframe_lands_on_the_cut.call_count == 0
        assert _ffmpeg_args(mock_ff)[_ffmpeg_args(mock_ff).index("-c") + 1] == "copy"

    def test_precise_mode_reencodes_even_when_a_copy_would_do(self, tmp_path):
        out = tmp_path / "out.mp4"
        with (
            patch("scripts.av.trim.has_video_stream", return_value=True),
            patch("scripts.av.trim.run_ffmpeg_with_progress") as mock_ff,
        ):
            strategy = trim(Path("in.mp4"), out, start="00:01", mode=MODE_PRECISE)
        assert strategy == "reencode"
        assert "-crf" in _ffmpeg_args(mock_ff)

    def test_reencode_of_an_audio_only_file_omits_crf(self, tmp_path):
        """-crf addresses a video encoder; an audio-only file has none."""
        out = tmp_path / "out.mp3"
        with (
            patch("scripts.av.trim.has_video_stream", return_value=False),
            patch("scripts.av.trim.run_ffmpeg_with_progress") as mock_ff,
        ):
            trim(Path("in.mp3"), out, start="00:01", mode=MODE_PRECISE)
        assert "-crf" not in _ffmpeg_args(mock_ff)

    def test_reencode_still_seeks_on_the_input_side(self, tmp_path):
        """Input seeking stays accurate under a re-encode, and stays fast."""
        out = tmp_path / "out.mp4"
        with (
            patch("scripts.av.trim.copy_would_land_on", return_value=(False, 0.0)),
            patch("scripts.av.trim.has_video_stream", return_value=True),
            patch("scripts.av.trim.run_ffmpeg_with_progress") as mock_ff,
        ):
            trim(Path("in.mp4"), out, start="00:01")
        args = _ffmpeg_args(mock_ff)
        assert args.index("-ss") < args.index("-i")

    def test_unknown_mode_is_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown trim mode"):
            trim(Path("in.mp4"), tmp_path / "out.mp4", start="00:01", mode="sloppy")
