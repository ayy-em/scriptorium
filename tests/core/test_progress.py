"""Tests for the script-to-UI progress contract.

Two audiences share one API: the streaming endpoint, which needs a sentinel line
it can pull off stdout, and a person at a terminal, who must never see one.
"""

import io

from core.invocation import CALLER_ENV_VAR
from core.progress import (
    SENTINEL,
    ProgressEvent,
    ProgressReporter,
    encode,
    parse,
)


class _Tty(io.StringIO):
    """A StringIO that claims to be a terminal."""

    def isatty(self) -> bool:
        return True


class TestEncodeAndParse:
    def test_round_trips(self):
        event = ProgressEvent(fraction=0.25, label="00:15 / 01:00")
        assert parse(encode(event)) == event

    def test_an_unknown_total_round_trips_as_none(self):
        assert parse(encode(ProgressEvent(fraction=None, label="working"))).fraction is None

    def test_ordinary_output_is_not_a_progress_event(self):
        assert parse("/home/user/outputs/av/clip.mp4") is None

    def test_a_trailing_newline_is_tolerated(self):
        assert parse(encode(ProgressEvent(fraction=0.5)) + "\n") is not None

    def test_malformed_json_is_ignored_rather_than_raised(self):
        """A mangled progress line should not fail a run that is otherwise fine."""
        assert parse(SENTINEL + "{not json") is None

    def test_a_non_object_payload_is_ignored(self):
        assert parse(SENTINEL + "[1, 2]") is None

    def test_a_non_numeric_fraction_is_ignored(self):
        assert parse(SENTINEL + '{"fraction": "half"}') is None

    def test_fraction_is_clamped_on_the_way_in(self):
        """A bar wider than its track is worse than one that sits at full.

        ffmpeg's reported position overshoots the probed duration routinely.
        """
        assert parse(SENTINEL + '{"fraction": 1.4}').fraction == 1.0
        assert parse(SENTINEL + '{"fraction": -0.2}').fraction == 0.0


class TestReporterForTheWebapp:
    def test_emits_a_sentinel_line(self):
        stream = io.StringIO()
        ProgressReporter(stream=stream, to_webapp=True).update(0.5, "halfway")
        assert parse(stream.getvalue()) == ProgressEvent(fraction=0.5, label="halfway")

    def test_detects_the_caller_from_the_environment(self, monkeypatch):
        monkeypatch.setenv(CALLER_ENV_VAR, "webapp")
        stream = io.StringIO()
        ProgressReporter(stream=stream).update(0.5)
        assert stream.getvalue().startswith(SENTINEL)

    def test_the_label_prefix_says_which_stage_is_moving(self):
        stream = io.StringIO()
        reporter = ProgressReporter(stream=stream, to_webapp=True, label_prefix="pass 2: ")
        reporter.update(0.5, "00:10")
        assert parse(stream.getvalue()).label == "pass 2: 00:10"

    def test_finish_reports_completion(self):
        stream = io.StringIO()
        ProgressReporter(stream=stream, to_webapp=True).finish("done")
        assert parse(stream.getvalue()) == ProgressEvent(fraction=1.0, label="done")


class TestThrottling:
    def test_a_second_update_inside_the_interval_is_dropped(self):
        stream = io.StringIO()
        reporter = ProgressReporter(stream=stream, to_webapp=True, min_interval=60.0)
        reporter.update(0.1)
        reporter.update(0.2)
        assert len(stream.getvalue().strip().splitlines()) == 1

    def test_a_forced_update_always_goes_out(self):
        stream = io.StringIO()
        reporter = ProgressReporter(stream=stream, to_webapp=True, min_interval=60.0)
        reporter.update(0.1)
        reporter.update(0.9, force=True)
        assert len(stream.getvalue().strip().splitlines()) == 2

    def test_a_repeated_whole_percent_is_dropped(self):
        """Most reports repeat the previous percent, since ffmpeg reports ~2/second."""
        stream = io.StringIO()
        reporter = ProgressReporter(stream=stream, to_webapp=True, min_interval=0.0)
        reporter.update(0.500)
        reporter.update(0.5001)
        assert len(stream.getvalue().strip().splitlines()) == 1

    def test_a_changed_percent_goes_out(self):
        stream = io.StringIO()
        reporter = ProgressReporter(stream=stream, to_webapp=True, min_interval=0.0)
        reporter.update(0.50)
        reporter.update(0.51)
        assert len(stream.getvalue().strip().splitlines()) == 2

    def test_unknown_fractions_are_not_deduplicated_by_percent(self):
        stream = io.StringIO()
        reporter = ProgressReporter(stream=stream, to_webapp=True, min_interval=0.0)
        reporter.update(None, "step 1")
        reporter.update(None, "step 2")
        assert len(stream.getvalue().strip().splitlines()) == 2


class TestReporterForAHuman:
    def test_never_emits_a_sentinel(self):
        stream = _Tty()
        ProgressReporter(stream=stream, to_webapp=False).update(0.42, "00:10")
        assert SENTINEL not in stream.getvalue()

    def test_writes_a_percentage_in_place(self):
        stream = _Tty()
        ProgressReporter(stream=stream, to_webapp=False).update(0.42, "00:10")
        written = stream.getvalue()
        assert written.startswith("\r")
        assert "42%" in written
        assert "00:10" in written

    def test_an_unknown_total_is_not_reported_as_zero_percent(self):
        stream = _Tty()
        ProgressReporter(stream=stream, to_webapp=False).update(None)
        assert "0%" not in stream.getvalue()

    def test_stays_silent_when_stderr_is_redirected(self):
        """Piping a script's output somewhere should not fill it with progress noise."""
        stream = io.StringIO()
        ProgressReporter(stream=stream, to_webapp=False).update(0.42)
        assert stream.getvalue() == ""

    def test_finish_closes_the_in_place_line(self):
        stream = _Tty()
        ProgressReporter(stream=stream, to_webapp=False).finish()
        assert stream.getvalue().endswith("\n")
