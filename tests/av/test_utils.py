"""Tests for scripts.av._utils shared helpers."""

import io
import json
from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from core.config import UserConfig
from core.progress import parse
from scripts.av import _utils
from scripts.av._utils import (
    av_inputs_dir,
    av_outputs_dir,
    find_media_files,
    format_clock,
    probe_duration,
    probe_duration_or_none,
    probe_streams,
    read_tags,
    run_ffmpeg,
    run_ffmpeg_with_progress,
    run_ffprobe,
)


def test_av_inputs_dir_creates_and_returns_path(tmp_path, monkeypatch):
    monkeypatch.setattr("core.paths._bundle_dir", lambda: tmp_path)
    d = av_inputs_dir()
    assert d.exists()
    assert d == tmp_path / "inputs"


def test_av_outputs_dir_creates_and_returns_path(tmp_path, monkeypatch):
    monkeypatch.setattr("core.paths._bundle_dir", lambda: tmp_path)
    monkeypatch.setattr("core.config.load", UserConfig)
    d = av_outputs_dir()
    assert d.exists()
    assert d == tmp_path / "outputs" / "av"


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
            capture_output=True,
            creationflags=mock_run.call_args.kwargs["creationflags"],
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


class TestFormatClock:
    def test_under_an_hour_omits_hours(self):
        assert format_clock(75) == "1:15"

    def test_an_hour_or_more_includes_hours(self):
        assert format_clock(3725) == "1:02:05"

    def test_sub_second_precision_is_dropped(self):
        assert format_clock(9.87) == "0:09"


class TestProbeDuration:
    def test_prefers_the_container_duration(self):
        data = {"format": {"duration": "12.5"}, "streams": [{"duration": "99.0"}]}
        with patch("scripts.av._utils.run_ffprobe", return_value=data):
            assert probe_duration(Path("clip.mp4")) == 12.5

    def test_falls_back_to_the_longest_stream(self):
        """A stream-copied file can carry stream durations without a container one."""
        data = {"format": {}, "streams": [{"duration": "5.0"}, {"duration": "8.0"}]}
        with patch("scripts.av._utils.run_ffprobe", return_value=data):
            assert probe_duration(Path("clip.mp4")) == 8.0

    def test_skips_streams_without_a_usable_duration(self):
        data = {"streams": [{"codec_type": "video"}, {"duration": "N/A"}, {"duration": "3.0"}]}
        with patch("scripts.av._utils.run_ffprobe", return_value=data):
            assert probe_duration(Path("clip.mp4")) == 3.0

    def test_raises_when_nothing_reports_a_duration(self):
        with patch("scripts.av._utils.run_ffprobe", return_value={"format": {}, "streams": []}):
            with pytest.raises(ValueError, match="Cannot determine duration"):
                probe_duration(Path("clip.mp4"))

    def test_or_none_swallows_the_failure(self):
        """An unknown duration costs a determinate bar, not the run."""
        with patch("scripts.av._utils.run_ffprobe", side_effect=OSError("ffprobe missing")):
            assert probe_duration_or_none(Path("clip.mp4")) is None


class _FakeFfmpeg:
    """Stands in for a Popen'd ffmpeg emitting a -progress stream."""

    def __init__(self, stdout: bytes, stderr: bytes = b"", returncode: int = 0):
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self._returncode = returncode

    def wait(self) -> int:
        return self._returncode


class TestRunFfmpegWithProgress:
    """These read the sentinel back off stdout, so the run looks like a webapp one."""

    @pytest.fixture(autouse=True)
    def _as_webapp(self, monkeypatch):
        monkeypatch.setenv("SCRIPTORIUM_CALLER", "webapp")

    def _run(self, stdout: bytes, capsys, **kwargs) -> list:
        fake = _FakeFfmpeg(stdout, **kwargs)
        with patch("scripts.av._utils.subprocess.Popen", return_value=fake):
            run_ffmpeg_with_progress(["-i", "in.mp4", "out.mp4"], total_seconds=10.0)
        return [event for event in (parse(line) for line in capsys.readouterr().out.splitlines()) if event]

    def test_asks_ffmpeg_for_a_machine_readable_progress_stream(self):
        fake = _FakeFfmpeg(b"")
        with patch("scripts.av._utils.subprocess.Popen", return_value=fake) as mock_popen:
            run_ffmpeg_with_progress(["-i", "in.mp4", "out.mp4"])
        cmd = mock_popen.call_args[0][0]
        assert cmd[:6] == ["ffmpeg", "-hide_banner", "-y", "-progress", "pipe:1", "-nostats"]

    def test_reports_position_as_a_fraction_of_the_total(self, capsys):
        events = self._run(b"out_time_us=5000000\nprogress=continue\n", capsys)
        assert events[0].fraction == 0.5
        assert events[0].label == "0:05 / 0:10"

    def test_out_time_ms_is_read_as_microseconds(self, capsys):
        """The out_time_ms field is misnamed in ffmpeg — it carries microseconds."""
        events = self._run(b"out_time_ms=5000000\nprogress=continue\n", capsys)
        assert events[0].fraction == 0.5

    def test_finishes_at_full(self, capsys):
        events = self._run(b"out_time_us=5000000\nprogress=end\n", capsys)
        assert events[-1].fraction == 1.0

    def test_ignores_the_other_progress_fields(self, capsys):
        events = self._run(b"bitrate=123.4kbits/s\nspeed=1.02x\ntotal_size=999\n", capsys)
        assert [e.fraction for e in events] == [1.0]

    def test_without_a_total_reports_position_but_no_fraction(self, capsys):
        fake = _FakeFfmpeg(b"out_time_us=7000000\n")
        with patch("scripts.av._utils.subprocess.Popen", return_value=fake):
            run_ffmpeg_with_progress(["-i", "in.mp4", "out.mp4"], total_seconds=None)
        events = [e for e in (parse(line) for line in capsys.readouterr().out.splitlines()) if e]
        assert events[0].fraction is None
        assert events[0].label == "0:07"

    def test_a_zero_total_does_not_divide_by_zero(self, capsys):
        fake = _FakeFfmpeg(b"out_time_us=1000000\n")
        with patch("scripts.av._utils.subprocess.Popen", return_value=fake):
            run_ffmpeg_with_progress(["-i", "in.mp4", "out.mp4"], total_seconds=0.0)
        assert [e.fraction for e in (parse(line) for line in capsys.readouterr().out.splitlines()) if e][0] is None

    def test_the_label_prefix_names_the_pass(self, capsys):
        fake = _FakeFfmpeg(b"out_time_us=5000000\n")
        with patch("scripts.av._utils.subprocess.Popen", return_value=fake):
            run_ffmpeg_with_progress(["-i", "in.mp4"], total_seconds=10.0, label_prefix="palette pass: ")
        events = [e for e in (parse(line) for line in capsys.readouterr().out.splitlines()) if e]
        assert events[0].label.startswith("palette pass: ")

    def test_a_failure_raises_with_ffmpeg_stderr_attached(self, capsys):
        fake = _FakeFfmpeg(b"", stderr=b"Invalid data found", returncode=1)
        with patch("scripts.av._utils.subprocess.Popen", return_value=fake):
            with pytest.raises(subprocess.CalledProcessError) as exc:
                run_ffmpeg_with_progress(["-i", "broken.mp4", "out.mp4"])
        assert exc.value.returncode == 1
        assert exc.value.stderr == b"Invalid data found"

    def test_a_failure_does_not_report_completion(self, capsys):
        fake = _FakeFfmpeg(b"", stderr=b"boom", returncode=1)
        with patch("scripts.av._utils.subprocess.Popen", return_value=fake):
            with pytest.raises(subprocess.CalledProcessError):
                run_ffmpeg_with_progress(["-i", "broken.mp4", "out.mp4"])
        assert [e for e in (parse(line) for line in capsys.readouterr().out.splitlines()) if e] == []


class TestHasVideoStream:
    """Cover art is a video stream to ffprobe but has no keyframes to seek to."""

    def test_true_for_a_real_video_track(self):
        streams = [{"codec_type": "video", "codec_name": "h264"}, {"codec_type": "audio"}]
        with patch("scripts.av._utils.probe_streams", return_value=streams):
            assert _utils.has_video_stream(Path("in.mp4")) is True

    def test_false_for_an_mp3_with_embedded_artwork(self):
        streams = [
            {"codec_type": "audio", "codec_name": "mp3"},
            {"codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}},
        ]
        with patch("scripts.av._utils.probe_streams", return_value=streams):
            assert _utils.has_video_stream(Path("in.mp3")) is False

    def test_false_when_the_probe_fails(self):
        with patch("scripts.av._utils.probe_streams", side_effect=OSError):
            assert _utils.has_video_stream(Path("missing.mp4")) is False


class TestKeyframeAtOrBefore:
    def test_zero_needs_no_probe(self):
        with patch("scripts.av._utils.run_ffprobe") as probe:
            assert _utils.keyframe_at_or_before(Path("in.mp4"), 0.0) == 0.0
        assert probe.call_count == 0

    def test_returns_the_last_keyframe_at_or_before_the_request(self):
        packets = {
            "packets": [
                {"pts_time": "0.000", "flags": "K__"},
                {"pts_time": "4.000", "flags": "K__"},
                {"pts_time": "5.000", "flags": "___"},
            ]
        }
        with patch("scripts.av._utils.run_ffprobe", return_value=packets):
            assert _utils.keyframe_at_or_before(Path("in.mp4"), 6.0) == 4.0

    def test_ignores_non_keyframe_packets(self):
        packets = {"packets": [{"pts_time": "5.900", "flags": "___"}, {"pts_time": "1.000", "flags": "K_"}]}
        with patch("scripts.av._utils.run_ffprobe", return_value=packets):
            assert _utils.keyframe_at_or_before(Path("in.mp4"), 6.0) == 1.0

    def test_reads_only_up_to_the_requested_point(self):
        """Cost must not grow with the length of the file after the cut."""
        with patch("scripts.av._utils.run_ffprobe", return_value={"packets": []}) as probe:
            _utils.keyframe_at_or_before(Path("in.mp4"), 12.0)
        args = probe.call_args[0][0]
        assert args[args.index("-read_intervals") + 1].startswith("%+12.1")

    def test_demuxes_rather_than_decodes(self):
        with patch("scripts.av._utils.run_ffprobe", return_value={"packets": []}) as probe:
            _utils.keyframe_at_or_before(Path("in.mp4"), 3.0)
        assert "-show_packets" in probe.call_args[0][0]

    def test_none_when_nothing_precedes_the_request(self):
        packets = {"packets": [{"pts_time": "9.000", "flags": "K_"}]}
        with patch("scripts.av._utils.run_ffprobe", return_value=packets):
            assert _utils.keyframe_at_or_before(Path("in.mp4"), 3.0) is None

    def test_none_when_ffprobe_cannot_be_asked(self):
        with patch("scripts.av._utils.run_ffprobe", side_effect=FileNotFoundError):
            assert _utils.keyframe_at_or_before(Path("in.mp4"), 3.0) is None


class TestCopyWouldLandOn:
    """The decision av.trim hangs its default behaviour on."""

    def test_start_of_file_is_always_exact(self):
        assert _utils.copy_would_land_on(Path("in.mp4"), 0.0) == (True, 0.0)

    def test_audio_only_needs_no_keyframe(self):
        """Audio frames are milliseconds long; there is no GOP to round to."""
        with (
            patch("scripts.av._utils.has_video_stream", return_value=False),
            patch("scripts.av._utils.keyframe_at_or_before") as kf,
        ):
            accurate, landing = _utils.copy_would_land_on(Path("in.mp3"), 30.0)
        assert accurate is True
        assert landing == 30.0
        assert kf.call_count == 0

    def test_a_nearby_keyframe_keeps_the_copy(self):
        with (
            patch("scripts.av._utils.has_video_stream", return_value=True),
            patch("scripts.av._utils.keyframe_at_or_before", return_value=9.95),
        ):
            assert _utils.copy_would_land_on(Path("in.mp4"), 10.0) == (True, 9.95)

    def test_a_distant_keyframe_fails_the_copy(self):
        """The reported bug: trimming a second off a sparsely-keyed file."""
        with (
            patch("scripts.av._utils.has_video_stream", return_value=True),
            patch("scripts.av._utils.keyframe_at_or_before", return_value=0.0),
        ):
            accurate, landing = _utils.copy_would_land_on(Path("in.mp4"), 1.0)
        assert accurate is False
        assert landing == 0.0

    def test_an_unknowable_keyframe_fails_the_copy(self):
        """Unable to verify is not the same as verified; prefer the exact cut."""
        with (
            patch("scripts.av._utils.has_video_stream", return_value=True),
            patch("scripts.av._utils.keyframe_at_or_before", return_value=None),
        ):
            assert _utils.copy_would_land_on(Path("in.mp4"), 10.0) == (False, None)
