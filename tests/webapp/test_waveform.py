"""Tests for webapp._waveform.

The point of reading peaks server-side is that the waveform stops depending on
what the browser can decode, so these cover the shape of the ffmpeg call, the
bucketing maths, and the failure modes a page has to render sensibly.
"""

import array
import subprocess
from unittest.mock import patch

import pytest

from webapp import _waveform


def _pcm(samples: list[int]) -> bytes:
    """Return signed 16-bit little-endian PCM for *samples*."""
    buffer = array.array("h", samples)
    if _waveform.sys.byteorder != "little":
        buffer.byteswap()
    return buffer.tobytes()


def _completed(stdout: bytes, returncode: int = 0, stderr: bytes = b"") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestDecodeRate:
    """The rate trades resolution against how much PCM lands in memory."""

    def test_short_file_is_capped_at_the_ceiling(self):
        assert _waveform._decode_rate(2.0, 900) == _waveform._MAX_RATE

    def test_long_file_falls_to_the_floor(self):
        # Two hours: the formula asks for 2.5 Hz, which would be low-passed
        # into a flat line.
        assert _waveform._decode_rate(7200.0, 900) == _waveform._MIN_RATE

    def test_unknown_duration_uses_the_ceiling(self):
        assert _waveform._decode_rate(0.0, 900) == _waveform._MAX_RATE

    def test_a_long_file_stays_within_a_bounded_sample_count(self):
        duration = 7200.0
        rate = _waveform._decode_rate(duration, 900)
        assert duration * rate <= 8_000_000


class TestBucketPeaks:
    def test_returns_one_value_per_bucket(self):
        peaks = _waveform._bucket_peaks(array.array("h", range(-500, 500)), 16)
        assert len(peaks) == 16

    def test_normalises_the_loudest_bucket_to_one(self):
        peaks = _waveform._bucket_peaks(array.array("h", [100] * 50 + [1000] * 50), 2)
        assert peaks == [pytest.approx(0.1), pytest.approx(1.0)]

    def test_uses_peaks_not_averages(self):
        """A waveform centred on zero averages to zero, drawing a flat line."""
        alternating = array.array("h", [16000, -16000] * 500)
        peaks = _waveform._bucket_peaks(alternating, 4)
        assert all(p == pytest.approx(1.0) for p in peaks)

    def test_negative_full_scale_is_clamped(self):
        """int16 reaches -32768 but only +32767, so -min can exceed full scale."""
        peaks = _waveform._bucket_peaks(array.array("h", [-32768] * 10), 2)
        assert all(0.0 <= p <= 1.0 for p in peaks)

    def test_no_samples_yields_no_peaks(self):
        assert _waveform._bucket_peaks(array.array("h"), 32) == []

    def test_silence_does_not_divide_by_zero(self):
        peaks = _waveform._bucket_peaks(array.array("h", [0] * 100), 8)
        assert peaks == [0.0] * 8

    def test_more_buckets_than_samples_still_fills_every_bucket(self):
        peaks = _waveform._bucket_peaks(array.array("h", [5, 9, 3]), 16)
        assert len(peaks) == 16


class TestReadWaveform:
    def test_decodes_to_mono_s16le_without_video(self):
        with (
            patch.object(_waveform, "probe_duration_or_none", return_value=10.0),
            patch.object(_waveform.subprocess, "run", return_value=_completed(_pcm([1000] * 2000))) as run,
        ):
            _waveform.read_waveform(_waveform.Path("in.mp3"), buckets=32)
        cmd = run.call_args[0][0]
        assert cmd[cmd.index("-ac") + 1] == "1"
        assert cmd[cmd.index("-f") + 1] == "s16le"
        assert "-vn" in cmd, "video would be decoded for nothing"
        assert cmd[-1] == "-"

    def test_buckets_are_clamped_to_a_sane_range(self):
        with (
            patch.object(_waveform, "probe_duration_or_none", return_value=1.0),
            patch.object(_waveform.subprocess, "run", return_value=_completed(_pcm([500] * 100))),
        ):
            result = _waveform.read_waveform(_waveform.Path("in.mp3"), buckets=100_000)
        assert len(result.peaks) == _waveform._MAX_BUCKETS

    def test_a_file_with_no_audio_yields_no_peaks_rather_than_an_error(self):
        """A silent-video trim should still get its time fields, not a stack trace."""
        with (
            patch.object(_waveform, "probe_duration_or_none", return_value=5.0),
            patch.object(_waveform.subprocess, "run", return_value=_completed(b"")),
        ):
            result = _waveform.read_waveform(_waveform.Path("silent.mp4"))
        assert result.peaks == []
        assert result.duration == 5.0

    def test_odd_trailing_byte_does_not_discard_the_stream(self):
        payload = _pcm([1000] * 100) + b"\x01"
        with (
            patch.object(_waveform, "probe_duration_or_none", return_value=1.0),
            patch.object(_waveform.subprocess, "run", return_value=_completed(payload)),
        ):
            result = _waveform.read_waveform(_waveform.Path("in.mp3"), buckets=16)
        assert len(result.peaks) == 16

    def test_ffmpeg_failure_raises_waveform_error_with_its_last_line(self):
        failure = _completed(b"", returncode=1, stderr=b"some noise\nInvalid data found\n")
        with (
            patch.object(_waveform, "probe_duration_or_none", return_value=None),
            patch.object(_waveform.subprocess, "run", return_value=failure),
            pytest.raises(_waveform.WaveformError, match="Invalid data found"),
        ):
            _waveform.read_waveform(_waveform.Path("broken.mp4"))

    def test_missing_ffmpeg_is_reported_as_a_waveform_error(self):
        with (
            patch.object(_waveform, "probe_duration_or_none", return_value=None),
            patch.object(_waveform.subprocess, "run", side_effect=FileNotFoundError),
            pytest.raises(_waveform.WaveformError, match="ffmpeg"),
        ):
            _waveform.read_waveform(_waveform.Path("in.mp3"))

    def test_partial_output_is_kept_when_ffmpeg_exits_nonzero(self):
        """A truncated recording still has a usable envelope worth drawing."""
        partial = _completed(_pcm([2000] * 500), returncode=1, stderr=b"truncated\n")
        with (
            patch.object(_waveform, "probe_duration_or_none", return_value=2.0),
            patch.object(_waveform.subprocess, "run", return_value=partial),
        ):
            result = _waveform.read_waveform(_waveform.Path("truncated.mp4"), buckets=16)
        assert len(result.peaks) == 16

    def test_duration_falls_back_to_the_decoded_stream(self):
        """A container can decline to state a duration; the PCM cannot."""
        with (
            patch.object(_waveform, "probe_duration_or_none", return_value=None),
            patch.object(_waveform.subprocess, "run", return_value=_completed(_pcm([1000] * 8000))),
        ):
            result = _waveform.read_waveform(_waveform.Path("in.mp3"), buckets=16)
        rate = _waveform._decode_rate(_waveform._FALLBACK_DURATION, 16)
        assert result.duration == pytest.approx(8000 / rate)

    def test_as_dict_is_the_json_shape_the_page_reads(self):
        with (
            patch.object(_waveform, "probe_duration_or_none", return_value=3.0),
            patch.object(_waveform.subprocess, "run", return_value=_completed(_pcm([1000] * 300))),
        ):
            payload = _waveform.read_waveform(_waveform.Path("in.mp3"), buckets=16).as_dict()
        assert sorted(payload) == ["duration", "peaks"]
        assert all(isinstance(p, float) for p in payload["peaks"])


class TestResolveStagedInput:
    """Which files the endpoint will read is the whole of its security."""

    def test_accepts_a_file_staged_in_the_inputs_tree(self, tmp_path):
        staged = tmp_path / "clip.mp4"
        staged.write_text("x")
        assert _waveform.resolve_staged_input(str(staged), tmp_path) == staged.resolve()

    def test_accepts_a_file_in_a_drop_session_subdirectory(self, tmp_path):
        session = tmp_path / "drop" / "abc123"
        session.mkdir(parents=True)
        staged = session / "clip.mp4"
        staged.write_text("x")
        assert _waveform.resolve_staged_input(str(staged), tmp_path) == staged.resolve()

    def test_refuses_a_path_outside_the_inputs_tree(self, tmp_path):
        outside = tmp_path.parent / "secret.mp4"
        outside.write_text("x")
        with pytest.raises(_waveform.StagedInputError) as excinfo:
            _waveform.resolve_staged_input(str(outside), tmp_path)
        assert excinfo.value.status == 403

    def test_refuses_a_traversal_out_of_the_inputs_tree(self, tmp_path):
        """Resolution must happen before containment, or '..' walks straight out."""
        secret = tmp_path.parent / "secret.mp4"
        secret.write_text("x")
        with pytest.raises(_waveform.StagedInputError) as excinfo:
            _waveform.resolve_staged_input(str(tmp_path / ".." / "secret.mp4"), tmp_path)
        assert excinfo.value.status == 403

    def test_refuses_a_symlink_pointing_out_of_the_inputs_tree(self, tmp_path):
        secret = tmp_path.parent / "secret.mp4"
        secret.write_text("x")
        link = tmp_path / "innocent.mp4"
        link.symlink_to(secret)
        with pytest.raises(_waveform.StagedInputError) as excinfo:
            _waveform.resolve_staged_input(str(link), tmp_path)
        assert excinfo.value.status == 403

    def test_refuses_an_empty_path(self, tmp_path):
        with pytest.raises(_waveform.StagedInputError) as excinfo:
            _waveform.resolve_staged_input("", tmp_path)
        assert excinfo.value.status == 400

    def test_refuses_a_directory(self, tmp_path):
        with pytest.raises(_waveform.StagedInputError) as excinfo:
            _waveform.resolve_staged_input(str(tmp_path), tmp_path)
        assert excinfo.value.status == 404

    def test_reports_a_missing_file_as_absent_not_forbidden(self, tmp_path):
        with pytest.raises(_waveform.StagedInputError) as excinfo:
            _waveform.resolve_staged_input(str(tmp_path / "gone.mp4"), tmp_path)
        assert excinfo.value.status == 404
