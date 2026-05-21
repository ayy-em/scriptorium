"""Tests for runner middleware (timing + persistent run logger + notify hook)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core import runner
from core.runner import _log_run, _timed, run_fn


@pytest.fixture
def log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect logs_dir() to a tmp path so each test has an isolated log file."""
    monkeypatch.setattr(runner, "logs_dir", lambda: tmp_path)
    return tmp_path


def _read_records(log_dir: Path) -> list[dict]:
    log = log_dir / "runs.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


class TestLogRun:
    def test_appends_record_with_schema(self, log_dir: Path):
        _log_run("foo.bar", 0.024, "done")
        records = _read_records(log_dir)
        assert len(records) == 1
        rec = records[0]
        assert rec["label"] == "foo.bar"
        assert rec["duration_s"] == 0.024
        assert rec["status"] == "done"
        assert "T" in rec["ts"]  # ISO-8601 timestamp

    def test_appends_multiple_records(self, log_dir: Path):
        _log_run("a", 0.1, "done")
        _log_run("b", 0.2, "failed")
        records = _read_records(log_dir)
        assert [r["label"] for r in records] == ["a", "b"]
        assert [r["status"] for r in records] == ["done", "failed"]

    def test_silent_on_failure(self, monkeypatch: pytest.MonkeyPatch):
        def boom() -> Path:
            raise PermissionError("disk full")

        monkeypatch.setattr(runner, "logs_dir", boom)
        _log_run("x", 0.0, "done")  # must not raise


class TestTimedLogging:
    def test_successful_run_logs_done(self, log_dir: Path):
        _timed("script.ok", lambda: 42)
        records = _read_records(log_dir)
        assert len(records) == 1
        assert records[0]["status"] == "done"
        assert records[0]["label"] == "script.ok"

    def test_exception_logs_failed_and_reraises(self, log_dir: Path):
        def raises() -> None:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            _timed("script.crash", raises)
        records = _read_records(log_dir)
        assert len(records) == 1
        assert records[0]["status"] == "failed"

    def test_system_exit_nonzero_logs_failed(self, log_dir: Path):
        def fails() -> None:
            raise SystemExit(1)

        with pytest.raises(SystemExit):
            _timed("script.exit1", fails)
        records = _read_records(log_dir)
        assert records[0]["status"] == "failed"

    def test_system_exit_zero_logs_done(self, log_dir: Path):
        def ok() -> None:
            raise SystemExit(0)

        with pytest.raises(SystemExit):
            _timed("script.exit0", ok)
        records = _read_records(log_dir)
        assert records[0]["status"] == "done"

    def test_run_fn_logs_module_qualified_label(self, log_dir: Path):
        def sample() -> int:
            return 7

        sample.__module__ = "scripts.demo.thing"
        run_fn(sample)
        records = _read_records(log_dir)
        assert records[0]["label"].startswith("demo.thing::")
        assert records[0]["label"].endswith("sample")


class TestNotifyHook:
    def test_no_notify_when_env_var_unset(self, log_dir: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("SCRIPTORIUM_NOTIFY", raising=False)
        with patch("scripts.util.notify.send") as mock_send:
            _timed("x", lambda: None)
        mock_send.assert_not_called()

    def test_notify_on_success_when_env_var_set(self, log_dir: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SCRIPTORIUM_NOTIFY", "1")
        with patch("scripts.util.notify.send") as mock_send:
            _timed("x", lambda: None)
        mock_send.assert_called_once()
        assert "done" in mock_send.call_args.args[0]

    def test_notify_on_failure(self, log_dir: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SCRIPTORIUM_NOTIFY", "1")

        def crash() -> None:
            raise RuntimeError("nope")

        with patch("scripts.util.notify.send") as mock_send, pytest.raises(RuntimeError):
            _timed("x", crash)

        mock_send.assert_called_once()
        assert "failed" in mock_send.call_args.args[0]

    def test_notify_failure_does_not_propagate(self, log_dir: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SCRIPTORIUM_NOTIFY", "1")
        with patch("scripts.util.notify.send", side_effect=RuntimeError("network down")):
            assert _timed("x", lambda: 42) == 42
