"""Tests for core.stdio — no character a script prints may crash its run."""

import io
import os
from pathlib import Path
import subprocess
import sys

import pytest

from core import stdio
from core.invocation import CALLER_ENV_VAR

_REPO_ROOT = Path(__file__).parent.parent.parent


def _ansi_pipe() -> io.TextIOWrapper:
    """Stand-in for a Windows pipe: cp1252, strict, as Python opens one."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")


def _patch_streams(monkeypatch: pytest.MonkeyPatch) -> tuple[io.TextIOWrapper, io.TextIOWrapper]:
    """Swap stdio for ANSI pipes.

    Called in the test body, not a fixture: pytest's capture resets sys.stdout
    between a fixture's setup and the test itself.
    """
    out, err = _ansi_pipe(), _ansi_pipe()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    return out, err


class TestConfigure:
    def test_a_webapp_run_writes_utf8(self, monkeypatch: pytest.MonkeyPatch):
        streams = _patch_streams(monkeypatch)
        monkeypatch.setenv(CALLER_ENV_VAR, "webapp")
        stdio.configure()
        out, err = streams
        assert out.encoding == "utf-8"
        assert err.encoding == "utf-8"
        out.write("trailing black → trimmed")
        out.flush()
        assert out.buffer.getvalue().decode("utf-8") == "trailing black → trimmed"

    def test_a_terminal_run_keeps_its_encoding_and_stops_crashing(self, monkeypatch: pytest.MonkeyPatch):
        streams = _patch_streams(monkeypatch)
        monkeypatch.delenv(CALLER_ENV_VAR, raising=False)
        stdio.configure()
        out, _ = streams
        assert out.encoding == "cp1252"
        out.write("a → b, ваш файл")
        out.flush()
        assert out.buffer.getvalue() == b"a ? b, ??? ????"

    def test_missing_streams_are_left_alone(self, monkeypatch: pytest.MonkeyPatch):
        """A windowed build may start with no stdio at all."""
        monkeypatch.setattr(sys, "stdout", None)
        monkeypatch.setattr(sys, "stderr", object())
        stdio.configure()


def _main(args: list[str], **env: str) -> subprocess.CompletedProcess[bytes]:
    """Run main.py with its output on a cp1252 pipe, as Windows gives one."""
    environ = {k: v for k, v in os.environ.items() if k not in (CALLER_ENV_VAR, "PYTHONUTF8")}
    environ.update(PYTHONIOENCODING="cp1252", **env)
    return subprocess.run(
        [sys.executable, str(_REPO_ROOT / "main.py"), *args],
        capture_output=True,
        env=environ,
        cwd=_REPO_ROOT,
        check=False,
        timeout=120,
    )


class TestMainOnAPipe:
    """End to end: av's listing holds a character cp1252 cannot encode."""

    def test_a_piped_listing_no_longer_crashes(self):
        result = _main(["av"])
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        assert b"av.trim" in result.stdout

    def test_the_webapp_gets_exactly_what_was_printed(self):
        result = _main(["av"], **{CALLER_ENV_VAR: "webapp"})
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        assert "−" in result.stdout.decode("utf-8")
