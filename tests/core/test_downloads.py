"""Tests for core.downloads: pooch's progress bar contract, driven by our reporter."""

import io
import sys
import types

from core import progress
from core.downloads import ReporterProgressBar, reporting_downloads


def _reporter(stream: io.StringIO) -> progress.ProgressReporter:
    return progress.ProgressReporter(stream=stream, to_webapp=True, min_interval=0.0)


class TestReporterProgressBar:
    def test_bytes_become_a_fraction_with_readable_sizes(self):
        stream = io.StringIO()
        bar = ReporterProgressBar(_reporter(stream), "Downloading u2net weights")
        bar.total = 4 * 1024 * 1024
        bar.update(1024 * 1024)
        event = progress.parse(stream.getvalue().strip())
        assert event.fraction == 0.25
        assert event.label == "Downloading u2net weights — 1 / 4 MB"

    def test_unknown_total_reports_indeterminate(self):
        stream = io.StringIO()
        bar = ReporterProgressBar(_reporter(stream), "Downloading")
        bar.update(2 * 1024 * 1024)
        event = progress.parse(stream.getvalue().strip())
        assert event.fraction is None
        assert event.label == "Downloading — 2 MB"

    def test_reset_then_fill_is_how_pooch_finishes(self):
        """Pooch resets, updates by the total, then closes; the result is 100%."""
        stream = io.StringIO()
        bar = ReporterProgressBar(_reporter(stream), "Downloading")
        bar.total = 100
        bar.update(60)
        bar.reset()
        bar.update(100)
        bar.close()
        last = progress.parse(stream.getvalue().strip().splitlines()[-1])
        assert last.fraction == 1.0


class TestReportingDownloads:
    def _fake_pooch(self, monkeypatch):
        calls = []
        module = types.SimpleNamespace(retrieve=lambda *a, **k: calls.append(k) or "path")
        monkeypatch.setitem(sys.modules, "pooch", module)
        return module, calls

    def test_progressbar_true_is_replaced_for_the_block(self, monkeypatch):
        module, calls = self._fake_pooch(monkeypatch)
        with reporting_downloads("Downloading"):
            module.retrieve("url", None, progressbar=True)
        assert isinstance(calls[0]["progressbar"], ReporterProgressBar)

    def test_other_progressbar_values_pass_through(self, monkeypatch):
        module, calls = self._fake_pooch(monkeypatch)
        with reporting_downloads("Downloading"):
            module.retrieve("url", None, progressbar=False)
        assert calls[0]["progressbar"] is False

    def test_the_original_is_restored_even_on_error(self, monkeypatch):
        module, _ = self._fake_pooch(monkeypatch)
        original = module.retrieve
        try:
            with reporting_downloads("Downloading"):
                raise RuntimeError("download failed")
        except RuntimeError:
            pass
        assert module.retrieve is original
