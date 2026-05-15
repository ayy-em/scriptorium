"""Tests for the frozen-app entrypoint helpers."""

import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent / "packaging"))
from entrypoint import (
    _find_chromium_browser,
    _find_free_port,
    _patch_missing_streams,
    _wait_for_server,
)


class TestFindFreePort:
    def test_returns_port_in_range(self):
        port = _find_free_port(49200, 49210)
        assert 49200 <= port < 49210

    def test_returns_start_when_all_busy(self):
        with patch("socket.socket") as mock_socket:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.bind.side_effect = OSError("in use")
            mock_socket.return_value = ctx
            port = _find_free_port(9000, 9002)
        assert port == 9000


class TestWaitForServer:
    def test_returns_true_when_started(self):
        server = MagicMock()
        server.started = True
        assert _wait_for_server(server, timeout=0.1) is True

    def test_returns_false_on_timeout(self):
        server = MagicMock()
        server.started = False
        assert _wait_for_server(server, timeout=0.1) is False


class TestPatchMissingStreams:
    def test_patches_none_stdout(self, monkeypatch):
        monkeypatch.setattr(sys, "stdout", None)
        _patch_missing_streams()
        assert sys.stdout is not None

    def test_patches_none_stderr(self, monkeypatch):
        monkeypatch.setattr(sys, "stderr", None)
        _patch_missing_streams()
        assert sys.stderr is not None

    def test_leaves_existing_streams(self):
        orig_out = sys.stdout
        orig_err = sys.stderr
        _patch_missing_streams()
        assert sys.stdout is orig_out
        assert sys.stderr is orig_err


class TestFindChromiumBrowser:
    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_returns_tuple_or_none_on_windows(self):
        result = _find_chromium_browser()
        if result is not None:
            name, path = result
            assert isinstance(name, str)
            assert isinstance(path, str)

    @pytest.mark.skipif(sys.platform == "win32", reason="Non-Windows only")
    def test_returns_tuple_or_none_on_unix(self):
        result = _find_chromium_browser()
        if result is not None:
            name, path = result
            assert isinstance(name, str)
            assert isinstance(path, str)
