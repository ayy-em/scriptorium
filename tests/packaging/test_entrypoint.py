"""Tests for the frozen-app entrypoint helpers."""

import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent / "packaging"))
from entrypoint import (
    _cli_args,
    _create_tray_icon,
    _create_tray_icon_for,
    _find_chromium_browser,
    _find_free_port,
    _patch_missing_streams,
    _start_gui,
    _stop_tray,
    _wait_for_server,
    _wants_cli,
)


class _Stream:
    """Minimal stdout stand-in with a controllable isatty()."""

    def __init__(self, tty: bool) -> None:
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


class _ClosedStream:
    """A stream whose isatty() raises, as a closed file object does."""

    def isatty(self) -> bool:
        raise ValueError("I/O operation on closed file")


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


class TestCliArgs:
    def test_drops_macos_process_serial_arg(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["Scriptorium", "-psn_0_1234567"])
        assert _cli_args() == []

    def test_keeps_real_args(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["scriptorium", "av.trim", "--help"])
        assert _cli_args() == ["av.trim", "--help"]


class TestWantsCli:
    def test_script_key_routes_to_cli(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["scriptorium", "av.trim"])
        monkeypatch.setattr(sys, "stdout", _Stream(tty=False))
        assert _wants_cli() is True

    def test_bare_tty_invocation_routes_to_cli(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["scriptorium"])
        monkeypatch.setattr(sys, "stdout", _Stream(tty=True))
        assert _wants_cli() is True

    def test_windowed_launch_with_redirected_stdio_routes_to_gui(self, monkeypatch):
        # macOS/Linux windowed launch: stdio is valid but points at /dev/null.
        # The old `sys.stdout is not None` check sent this to the CLI, so the
        # .app printed the script list to nowhere and exited without a window.
        monkeypatch.setattr(sys, "argv", ["Scriptorium"])
        monkeypatch.setattr(sys, "stdout", _Stream(tty=False))
        assert _wants_cli() is False

    def test_macos_finder_launch_routes_to_gui(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["Scriptorium", "-psn_0_1234567"])
        monkeypatch.setattr(sys, "stdout", _Stream(tty=False))
        assert _wants_cli() is False

    def test_windows_windowed_build_routes_to_gui(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["ScriptoriumApp"])
        monkeypatch.setattr(sys, "stdout", None)
        assert _wants_cli() is False

    def test_closed_stream_routes_to_gui(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["Scriptorium"])
        monkeypatch.setattr(sys, "stdout", _ClosedStream())
        assert _wants_cli() is False


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


class TestCreateTrayIconFor:
    """The threading model here is load-bearing, not a detail.

    pystray's macOS backend calls -[NSApplication run] inside Icon.run, which
    AppKit only tolerates on the main thread; off it, the process takes SIGTRAP
    and no except clause can save it.
    """

    def _fake_pystray(self):
        module = MagicMock()
        module.Icon.return_value = MagicMock()
        return module

    def _patched(self, module):
        return patch.dict(sys.modules, {"pystray": module})

    def test_detached_does_not_spawn_a_thread(self):
        module = self._fake_pystray()
        with (
            self._patched(module),
            patch("entrypoint._load_tray_icon", return_value=MagicMock()),
            patch("threading.Thread") as thread,
        ):
            tray = _create_tray_icon_for(MagicMock(), MagicMock(), detached=True)

        thread.assert_not_called()
        tray.run_detached.assert_called_once_with()

    def test_non_detached_runs_on_a_background_thread(self):
        module = self._fake_pystray()
        with (
            self._patched(module),
            patch("entrypoint._load_tray_icon", return_value=MagicMock()),
            patch("threading.Thread") as thread,
        ):
            tray = _create_tray_icon_for(MagicMock(), MagicMock())

        thread.assert_called_once()
        assert thread.call_args.kwargs["target"] is tray.run
        tray.run_detached.assert_not_called()

    def test_returns_none_without_an_icon_image(self):
        module = self._fake_pystray()
        with self._patched(module), patch("entrypoint._load_tray_icon", return_value=None):
            assert _create_tray_icon_for(MagicMock(), MagicMock()) is None


class TestCreateTrayIcon:
    def test_macos_window_tray_is_detached(self):
        with patch("entrypoint._create_tray_icon_for") as create, patch("entrypoint._MACOS", True):
            _create_tray_icon(MagicMock())
        assert create.call_args.kwargs["detached"] is True

    def test_other_platforms_use_a_thread(self):
        with patch("entrypoint._create_tray_icon_for") as create, patch("entrypoint._MACOS", False):
            _create_tray_icon(MagicMock())
        assert create.call_args.kwargs["detached"] is False


class TestTrayIconIsNotLeakedBetweenTiers:
    """One running app must never show two tray icons.

    The pywebview tier creates its icon *before* ``webview.start()``, because the
    closing handler needs it. On Windows the frozen build is exactly where
    ``start()`` fails, so the error path has to take the icon down before the
    Chromium tier creates its own — otherwise the user gets two, and the first
    one's menu drives a window that never opened.
    """

    def _start_gui_with_failing_webview(self, tier1_tray):
        fake_webview = MagicMock()
        fake_webview.start.side_effect = RuntimeError("Failed to initialize Python.Runtime.dll")
        with (
            patch.dict(sys.modules, {"webview": fake_webview}),
            patch("entrypoint._patch_webview2_external_drop"),
            patch("entrypoint._create_tray_icon", return_value=tier1_tray),
            patch("entrypoint._chromium_app_window") as chromium,
            patch("entrypoint._MACOS", False),
        ):
            _start_gui(MagicMock(), "http://127.0.0.1:1", MagicMock(), MagicMock(), MagicMock())
        return chromium

    def test_failed_pywebview_tier_stops_its_icon(self):
        tier1_tray = MagicMock()
        chromium = self._start_gui_with_failing_webview(tier1_tray)
        assert chromium.called, "should have fallen through to the Chromium tier"
        tier1_tray.stop.assert_called_once_with()

    def test_an_unstoppable_icon_does_not_block_the_next_tier(self):
        """stop() can raise if Icon.run has not reached its loop yet."""
        tier1_tray = MagicMock()
        tier1_tray.stop.side_effect = RuntimeError("icon not running")
        chromium = self._start_gui_with_failing_webview(tier1_tray)
        assert chromium.called

    def test_no_icon_when_pywebview_fails_before_creating_one(self):
        """create_window failing must not NameError on the unbound icon."""
        fake_webview = MagicMock()
        fake_webview.create_window.side_effect = RuntimeError("no window")
        with (
            patch.dict(sys.modules, {"webview": fake_webview}),
            patch("entrypoint._patch_webview2_external_drop"),
            patch("entrypoint._chromium_app_window") as chromium,
            patch("entrypoint._MACOS", False),
        ):
            _start_gui(MagicMock(), "http://127.0.0.1:1", MagicMock(), MagicMock(), MagicMock())
        assert chromium.called


class TestStopTray:
    def test_none_is_a_no_op(self):
        _stop_tray(None)

    def test_swallows_a_failing_stop(self):
        tray = MagicMock()
        tray.stop.side_effect = RuntimeError("not running")
        _stop_tray(tray)
        tray.stop.assert_called_once_with()


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
