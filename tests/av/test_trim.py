"""Tests for scripts.av.trim.

Two things are asserted here. Input-side seeking: ``-ss`` before ``-i`` so
ffmpeg starts from the nearest keyframe, and ``-t <duration>`` rather than
``-to <absolute>`` to match input-side semantics (see commit d891096). And the
accuracy decision: a stream copy begins at a keyframe, so when the nearest one
is not where the user asked, the cut is re-encoded instead of silently rounded.
"""

from pathlib import Path
import shutil
import subprocess
from unittest.mock import patch

import pytest

from scripts.av import _utils
from scripts.av import trim as trim_module
from scripts.av.trim import MODE_FAST, MODE_PRECISE, STRATEGY_SMART, trim


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
            patch("scripts.av.trim._smart_cut", return_value="vp9 video cannot be spliced"),
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
            patch("scripts.av.trim._smart_cut", return_value="no keyframe follows the start"),
            patch("scripts.av.trim.run_ffmpeg_with_progress") as mock_ff,
        ):
            trim(Path("in.mp4"), out, start="00:01")
        args = _ffmpeg_args(mock_ff)
        assert args.index("-ss") < args.index("-i")

    def test_unknown_mode_is_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown trim mode"):
            trim(Path("in.mp4"), tmp_path / "out.mp4", start="00:01", mode="sloppy")


class TestSmartCut:
    """auto re-encodes only up to the next keyframe when a plain copy would miss."""

    def test_auto_prefers_a_smart_cut_over_a_full_reencode(self, tmp_path):
        out = tmp_path / "out.mp4"
        with (
            patch("scripts.av.trim.copy_would_land_on", return_value=(False, 0.0)),
            patch("scripts.av.trim.has_video_stream", return_value=True),
            patch("scripts.av.trim._smart_cut", return_value=None) as smart,
            patch("scripts.av.trim.run_ffmpeg_with_progress") as full,
        ):
            strategy = trim(Path("in.mp4"), out, start="3.3", end="20")
        assert strategy == STRATEGY_SMART
        smart.assert_called_once_with(Path("in.mp4"), out, 3.3, 20.0)
        full.assert_not_called()

    def test_falls_back_to_a_full_reencode_and_says_why(self, tmp_path, capsys):
        out = tmp_path / "out.mp4"
        with (
            patch("scripts.av.trim.copy_would_land_on", return_value=(False, 0.0)),
            patch("scripts.av.trim.has_video_stream", return_value=True),
            patch("scripts.av.trim._smart_cut", return_value="the cut ends before the next keyframe"),
            patch("scripts.av.trim.run_ffmpeg_with_progress") as full,
        ):
            assert trim(Path("in.mp4"), out, start="00:03") == "reencode"
        full.assert_called_once()
        assert "the cut ends before the next keyframe" in capsys.readouterr().out

    @pytest.mark.parametrize("mode", [MODE_FAST, MODE_PRECISE])
    def test_explicit_modes_never_smart_cut(self, tmp_path, mode):
        with (
            patch("scripts.av.trim.copy_would_land_on", return_value=(False, 0.0)),
            patch("scripts.av.trim.has_video_stream", return_value=True),
            patch("scripts.av.trim._smart_cut") as smart,
            patch("scripts.av.trim.run_ffmpeg_with_progress"),
        ):
            trim(Path("in.mp4"), tmp_path / "out.mp4", start="00:03", mode=mode)
        smart.assert_not_called()

    def test_unsupported_codec_is_not_spliced(self):
        with patch("scripts.av.trim.probe_streams", return_value=[{"codec_type": "video", "codec_name": "vp9"}]):
            assert trim_module._plan_smart_cut(Path("in.webm"), 3.0, None) == "vp9 video cannot be spliced"

    def test_a_cut_ending_before_the_next_keyframe_is_not_spliced(self):
        with (
            patch("scripts.av.trim.probe_streams", return_value=[{"codec_type": "video", "codec_name": "h264"}]),
            patch("scripts.av.trim.keyframe_after", return_value=8.0),
        ):
            assert "ends before" in trim_module._plan_smart_cut(Path("in.mp4"), 3.0, 6.0)

    def test_a_splice_that_fails_verification_leaves_no_file(self, tmp_path):
        out = tmp_path / "out.mp4"

        def fake_ffmpeg(args):
            Path(args[-1]).write_bytes(b"x")

        with (
            patch(
                "scripts.av.trim.probe_streams",
                return_value=[{"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p"}],
            ),
            patch("scripts.av.trim.keyframe_after", return_value=8.0),
            patch("scripts.av.trim.run_ffmpeg", side_effect=fake_ffmpeg),
            patch("scripts.av.trim.run_ffmpeg_stderr", return_value="Invalid NAL unit size"),
        ):
            reason = trim_module._smart_cut(Path("in.mp4"), out, 3.0, 20.0)
        assert reason == "the spliced file did not decode cleanly"
        assert not out.exists()


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="needs ffmpeg")
def test_smart_cut_end_to_end_is_exact_and_decodes_cleanly(tmp_path):
    """Real ffmpeg on a source with one keyframe every eight seconds."""
    src = tmp_path / "sparse.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=20",
         "-f", "lavfi", "-i", "sine=frequency=300:duration=20",
         "-c:v", "libx264", "-preset", "ultrafast", "-g", "240", "-keyint_min", "240", "-sc_threshold", "0",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)],
        check=True,
    )  # fmt: skip
    out = tmp_path / "cut.mp4"

    # The module-wide stub would hide the length check this test is partly about.
    with patch("scripts.av.trim.probe_duration_or_none", _utils.probe_duration_or_none):
        assert trim_module._smart_cut(src, out, 3.3, 15.0) is None

    decode = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(out), "-f", "null", "-"], capture_output=True, text=True, check=False
    )
    assert decode.stderr == ""
    duration = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert float(duration) == pytest.approx(11.7, abs=0.2)
