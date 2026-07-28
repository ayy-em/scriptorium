"""Tests for the live run registry and process-tree termination."""

import contextlib
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from webapp import _runs

# os.getpgid/os.killpg and signal.SIGKILL do not exist on Windows, so the POSIX
# branch is exercised against stand-ins. That keeps the dispatch logic under
# test on every platform; real signal delivery is a manual check (HUMAN_TODO).
_SIGTERM = 15
_SIGKILL = 9


@contextlib.contextmanager
def _posix(grace=None, poll=None, getpgid_error=None):
    """Run a block as if on POSIX, with the process APIs stubbed out.

    Args:
        grace: Override for the SIGTERM grace period, in seconds.
        poll: Override for the liveness poll interval, in seconds.
        getpgid_error: Exception for ``os.getpgid`` to raise, if any.

    Yields:
        Dict of the patched ``getpgid`` and ``killpg`` mocks.
    """
    getpgid = MagicMock(return_value=555, side_effect=getpgid_error)
    killpg = MagicMock()
    stack = [
        patch.object(_runs.sys, "platform", "linux"),
        patch.object(_runs, "signal", SimpleNamespace(SIGTERM=_SIGTERM, SIGKILL=_SIGKILL)),
        patch.object(_runs.os, "getpgid", getpgid, create=True),
        patch.object(_runs.os, "killpg", killpg, create=True),
    ]
    if grace is not None:
        stack.append(patch.object(_runs, "_GRACE_SECONDS", grace))
    if poll is not None:
        stack.append(patch.object(_runs, "_POLL_SECONDS", poll))

    with contextlib.ExitStack() as es:
        for ctx in stack:
            es.enter_context(ctx)
        yield {"getpgid": getpgid, "killpg": killpg}


@pytest.fixture(autouse=True)
def clean_registry():
    """Keep the module-level registry from leaking between tests."""
    _runs._ACTIVE.clear()
    yield
    _runs._ACTIVE.clear()


def _handle(returncode=None, pid=4242):
    handle = _runs.new_handle("av.filmstrip", ["clip.mp4"], {"source": "clip.mp4"})
    proc = MagicMock()
    proc.pid = pid
    proc.returncode = returncode
    handle.process = proc
    return handle


class TestRegistry:
    def test_new_handle_is_registered(self):
        handle = _runs.new_handle("av.trim", [], {})
        assert _runs.get(handle.run_id) is handle

    def test_run_ids_are_unique(self):
        ids = {_runs.new_handle("av.trim", [], {}).run_id for _ in range(50)}
        assert len(ids) == 50

    def test_copies_argv_and_params(self):
        argv, params = ["a"], {"k": "v"}
        handle = _runs.new_handle("av.trim", argv, params)
        argv.append("mutated")
        params["k"] = "mutated"
        assert handle.argv == ["a"]
        assert handle.params == {"k": "v"}

    def test_get_unknown_returns_none(self):
        assert _runs.get("nope") is None

    def test_discard_removes(self):
        handle = _runs.new_handle("av.trim", [], {})
        _runs.discard(handle.run_id)
        assert _runs.get(handle.run_id) is None

    def test_discard_is_idempotent(self):
        handle = _runs.new_handle("av.trim", [], {})
        _runs.discard(handle.run_id)
        _runs.discard(handle.run_id)

    def test_active_ids_tracks_concurrent_runs(self):
        a = _runs.new_handle("av.trim", [], {})
        b = _runs.new_handle("av.split", [], {})
        assert set(_runs.active_ids()) == {a.run_id, b.run_id}

    def test_handles_start_not_cancelled(self):
        assert _runs.new_handle("av.trim", [], {}).cancelled is False


class TestSpawnKwargs:
    def test_windows_suppresses_the_console_window(self):
        with patch.object(_runs.sys, "platform", "win32"):
            assert _runs.spawn_kwargs() == {"creationflags": subprocess.CREATE_NO_WINDOW}

    @pytest.mark.parametrize("platform", ["linux", "darwin"])
    def test_posix_starts_a_new_session(self, platform):
        """A new session means a new process group, which is what killpg needs."""
        with patch.object(_runs.sys, "platform", platform):
            assert _runs.spawn_kwargs() == {"start_new_session": True}


class TestTerminateTree:
    def test_marks_cancelled_even_when_there_is_nothing_to_kill(self):
        handle = _runs.new_handle("av.trim", [], {})
        assert _runs.terminate_tree(handle) is False
        assert handle.cancelled is True

    def test_already_exited_process_is_not_signalled(self):
        handle = _handle(returncode=0)
        assert _runs.terminate_tree(handle) is False
        assert handle.cancelled is True

    def test_windows_uses_taskkill_with_the_tree_flag(self):
        handle = _handle(pid=1234)
        with (
            patch.object(_runs.sys, "platform", "win32"),
            patch.object(_runs.subprocess, "run") as run,
        ):
            run.return_value = MagicMock(returncode=0, stderr=b"")
            assert _runs.terminate_tree(handle) is True
        cmd = run.call_args[0][0]
        assert cmd[0] == "taskkill"
        # /T is the whole point: without it ffmpeg survives its parent.
        assert "/T" in cmd
        assert "/F" in cmd
        assert cmd[-1] == "1234"

    def test_windows_reports_failure(self):
        handle = _handle(pid=1234)
        with (
            patch.object(_runs.sys, "platform", "win32"),
            patch.object(_runs.subprocess, "run") as run,
        ):
            run.return_value = MagicMock(returncode=128, stderr=b"not found")
            assert _runs.terminate_tree(handle) is False

    def test_posix_signals_the_whole_group(self):
        handle = _handle(pid=555)
        with _posix() as posix:
            # Group is gone right after SIGTERM, so no escalation.
            posix["killpg"].side_effect = [None, ProcessLookupError()]
            assert _runs.terminate_tree(handle) is True
        posix["getpgid"].assert_called_once_with(555)
        assert posix["killpg"].call_args_list[0][0] == (555, _SIGTERM)

    def test_posix_escalates_to_sigkill_when_the_group_lingers(self):
        handle = _handle(pid=555)
        with _posix(grace=0.05, poll=0.01) as posix:
            # killpg never raises, so the group always looks alive.
            assert _runs.terminate_tree(handle) is True
        sent = [call[0][1] for call in posix["killpg"].call_args_list]
        assert _SIGTERM in sent
        assert _SIGKILL in sent

    def test_posix_handles_a_process_that_vanished(self):
        handle = _handle(pid=555)
        with _posix(getpgid_error=ProcessLookupError()):
            assert _runs.terminate_tree(handle) is False

    def test_unexpected_failure_is_swallowed_but_still_cancels(self):
        handle = _handle(pid=1234)
        with (
            patch.object(_runs.sys, "platform", "win32"),
            patch.object(_runs.subprocess, "run", side_effect=OSError("boom")),
        ):
            assert _runs.terminate_tree(handle) is False
        assert handle.cancelled is True
