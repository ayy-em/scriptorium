"""Tests for the entrypoint's single-instance handling and Chromium hand-off detection."""

from pathlib import Path
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "packaging"))
import entrypoint  # noqa: E402
from entrypoint import (  # noqa: E402
    _chromium_profile_in_use,
    _ChromiumWindow,
    _handed_off,
    _wait_for_profile_release,
)


class TestChromiumProfileInUse:
    def test_windows_lockfile_held_exclusively_means_in_use(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        with patch("os.open", side_effect=PermissionError):
            assert _chromium_profile_in_use("C:/profile") is True

    def test_windows_lockfile_absent_means_free(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        with patch("os.open", side_effect=FileNotFoundError):
            assert _chromium_profile_in_use("C:/profile") is False

    def test_posix_singleton_lock_pointing_at_a_live_pid(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        with patch("os.readlink", return_value="myhost-4242"), patch("os.kill") as kill:
            assert _chromium_profile_in_use("/profile") is True
        kill.assert_called_once_with(4242, 0)

    def test_posix_singleton_lock_of_a_dead_pid(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        with patch("os.readlink", return_value="myhost-4242"), patch("os.kill", side_effect=ProcessLookupError):
            assert _chromium_profile_in_use("/profile") is False

    def test_posix_no_singleton_lock(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        with patch("os.readlink", side_effect=FileNotFoundError):
            assert _chromium_profile_in_use("/profile") is False


class TestHandedOff:
    """A second launch on a busy profile exits with 0 in ~0.1s (measured on Windows Chrome)."""

    def test_quick_clean_exit_on_a_busy_profile(self):
        with patch("entrypoint._chromium_profile_in_use", return_value=True):
            assert _handed_off(0.1, 0, "p") is True

    def test_a_window_that_lived_was_really_closed(self):
        with patch("entrypoint._chromium_profile_in_use", return_value=True):
            assert _handed_off(120.0, 0, "p") is False

    def test_a_crash_is_not_a_handoff(self):
        with patch("entrypoint._chromium_profile_in_use", return_value=True):
            assert _handed_off(0.1, 1, "p") is False

    def test_a_free_profile_is_not_a_handoff(self):
        with patch("entrypoint._chromium_profile_in_use", return_value=False):
            assert _handed_off(0.1, 0, "p") is False


class TestWaitForProfileRelease:
    def test_returns_once_the_browser_lets_go(self):
        answers = iter([True, True, False])
        with patch("entrypoint._chromium_profile_in_use", side_effect=lambda _p: next(answers)):
            _wait_for_profile_release("p", threading.Event(), poll=0.01)

    def test_quit_stops_the_wait(self):
        stop = threading.Event()
        stop.set()
        with patch("entrypoint._chromium_profile_in_use", return_value=True):
            _wait_for_profile_release("p", stop, poll=0.01)


class TestChromiumWindowShow:
    @pytest.fixture
    def window(self):
        return _ChromiumWindow("Chrome", "chrome.exe", "http://127.0.0.1:1", "profile", MagicMock())

    def test_a_closed_window_is_reopened_by_the_tray_loop(self, window):
        reopen = threading.Event()
        window.show(reopen)
        assert reopen.is_set()

    def test_an_open_window_is_raised_not_duplicated(self, window):
        window.proc = MagicMock(pid=99)
        window.is_open.set()
        with patch("entrypoint._focus_windows_of", return_value=True) as focus, patch("subprocess.Popen") as popen:
            window.show(threading.Event())
        focus.assert_called_once_with(99)
        popen.assert_not_called()

    def test_an_unraisable_window_gets_a_new_one_rather_than_nothing(self, window):
        window.proc = MagicMock(pid=99)
        window.is_open.set()
        with patch("entrypoint._focus_windows_of", return_value=False), patch("subprocess.Popen") as popen:
            window.show(threading.Event())
        popen.assert_called_once_with(window.cmd)

    def test_wait_closed_watches_the_profile_after_a_handoff(self, window):
        window.proc = MagicMock(returncode=0)
        window.is_open.set()
        with (
            patch("entrypoint._handed_off", return_value=True),
            patch("entrypoint._wait_for_profile_release") as wait_release,
        ):
            assert window.wait_closed(threading.Event()) is True
        wait_release.assert_called_once()
        assert not window.is_open.is_set()


class TestMainSingleInstance:
    @pytest.fixture(autouse=True)
    def _windowed_launch(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["Scriptorium"])
        monkeypatch.setattr(entrypoint, "_wants_cli", lambda: False)
        monkeypatch.setattr(entrypoint, "_patch_missing_streams", lambda: None)

    def test_a_second_launch_hands_over_and_starts_nothing(self):
        with (
            patch("core.instance.acquire", return_value=None),
            patch("core.instance.show_running_instance", return_value=True),
            patch("entrypoint._find_free_port") as find_port,
            patch("entrypoint._start_gui") as start_gui,
        ):
            entrypoint.main()
        find_port.assert_not_called()
        start_gui.assert_not_called()

    def test_the_owner_publishes_its_port_and_releases_on_exit(self):
        lock = MagicMock()
        with (
            patch("core.instance.acquire", return_value=lock),
            patch("entrypoint._find_free_port", return_value=57234),
            patch("entrypoint._run_server"),
            patch("entrypoint._wait_for_server", return_value=True),
            patch("entrypoint._start_gui") as start_gui,
        ):
            entrypoint.main()
        lock.publish.assert_called_once_with(57234)
        start_gui.assert_called_once()
        lock.release.assert_called_once()

    def test_an_unanswering_owner_that_has_died_is_replaced(self):
        """The lock is retried once before giving up on it."""
        lock = MagicMock()
        with (
            patch("core.instance.acquire", side_effect=[None, lock]),
            patch("core.instance.show_running_instance", return_value=False),
            patch("entrypoint._find_free_port", return_value=57235),
            patch("entrypoint._run_server"),
            patch("entrypoint._wait_for_server", return_value=True),
            patch("entrypoint._start_gui"),
        ):
            entrypoint.main()
        lock.publish.assert_called_once_with(57235)
