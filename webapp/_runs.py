"""Live run registry and process-tree termination.

A script run is not one process. ``main.py`` spawns the script, which in turn
shells out to ffmpeg or yt-dlp, so killing the direct child leaves the real
worker running and writing to disk. Everything here exists to kill the whole
tree instead.

Completed runs move out of here and into ``core.history``; this module only
knows about runs currently in flight.
"""

from dataclasses import dataclass, field
from datetime import datetime
import logging
import os
import signal
import subprocess
import sys
import time
import uuid

logger = logging.getLogger(__name__)

# How long a process group gets to honour SIGTERM before SIGKILL. Long enough
# for ffmpeg to close its output file cleanly, short enough not to feel stuck.
_GRACE_SECONDS = 3.0
_POLL_SECONDS = 0.1


@dataclass
class RunHandle:
    """A script run currently in flight.

    Attributes:
        run_id: Opaque identifier, shared with the client so it can cancel.
        key: Dotted script key such as ``"av.filmstrip"``.
        argv: CLI arguments passed after the key.
        params: Original form values, carried through to the history record.
        started_at: When the run began.
        process: The spawned ``asyncio.subprocess.Process``, once it exists.
        cancelled: True once cancellation has been requested. The stream reader
            uses this to report ``cancelled`` rather than a spurious failure,
            since a killed process still exits non-zero.
        batch_id: Shared by every run of one per-file fan-out, empty otherwise.
            Carried through to the history record so a batch can be grouped.
    """

    run_id: str
    key: str
    argv: list[str] = field(default_factory=list)
    params: dict[str, str] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
    process: object | None = None
    cancelled: bool = False
    batch_id: str = ""


_ACTIVE: dict[str, RunHandle] = {}


def new_handle(key: str, argv: list[str], params: dict[str, str], *, batch_id: str = "") -> RunHandle:
    """Create and register a handle for a run about to start.

    Args:
        key: Dotted script key.
        argv: CLI arguments after the key.
        params: Original form values.
        batch_id: Groups this run with the rest of its fan-out, if any.

    Returns:
        The registered handle.
    """
    handle = RunHandle(
        run_id=uuid.uuid4().hex[:12],
        key=key,
        argv=list(argv),
        params=dict(params),
        batch_id=batch_id,
    )
    _ACTIVE[handle.run_id] = handle
    return handle


def get(run_id: str) -> RunHandle | None:
    """Return the in-flight handle for *run_id*, or None if it is not running.

    A finished run is not here — it is in ``core.history``.

    Args:
        run_id: Identifier to look up.

    Returns:
        The handle, or None.
    """
    return _ACTIVE.get(run_id)


def discard(run_id: str) -> None:
    """Remove a handle from the registry. Safe to call twice.

    Args:
        run_id: Identifier to drop.
    """
    _ACTIVE.pop(run_id, None)


def active_ids() -> list[str]:
    """Return the ids of every run currently in flight.

    Returns:
        Run ids, unordered.
    """
    return list(_ACTIVE)


def spawn_kwargs() -> dict:
    """Return the Popen keyword arguments needed to make a run killable.

    On POSIX the child leads a new process group, so one ``killpg`` reaches
    every descendant. On Windows the tree is walked by ``taskkill`` instead;
    the flag here only suppresses a console window flashing up in the packaged
    app.

    Returns:
        Keyword arguments to pass to ``asyncio.create_subprocess_exec``.
    """
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}


def _kill_windows(pid: int) -> bool:
    """Kill a process and its descendants via taskkill.

    ``TerminateProcess`` — which is all that ``Process.kill()`` does on Windows
    — stops only the named process, orphaning any ffmpeg it started. ``/T``
    walks the tree.

    Args:
        pid: Process id of the direct child.

    Returns:
        True if taskkill reported success.
    """
    result = subprocess.run(
        ["taskkill", "/T", "/F", "/PID", str(pid)],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )
    if result.returncode != 0:
        logger.debug("taskkill on %s returned %s: %s", pid, result.returncode, result.stderr)
    return result.returncode == 0


def _group_alive(pgid: int) -> bool:
    """Report whether any process remains in the group.

    Args:
        pgid: Process group id.

    Returns:
        True if signal 0 can still be delivered to the group.
    """
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError, PermissionError:
        return False
    return True


def _kill_posix(pid: int) -> bool:
    """Terminate a process group, escalating to SIGKILL if it lingers.

    Args:
        pid: Process id of the group leader.

    Returns:
        True if a signal was delivered.
    """
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return False

    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return False

    deadline = time.monotonic() + _GRACE_SECONDS
    while time.monotonic() < deadline:
        if not _group_alive(pgid):
            return True
        time.sleep(_POLL_SECONDS)

    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return True


def terminate_tree(handle: RunHandle) -> bool:
    """Cancel a run, killing the script and everything it spawned.

    Marks the handle cancelled first, so that even a partially successful kill
    is reported as a cancellation rather than a crash.

    Blocking: call it off the event loop (``asyncio.to_thread``).

    Args:
        handle: The in-flight run to stop.

    Returns:
        True if the process tree was signalled, False if there was nothing
        left to kill.
    """
    handle.cancelled = True
    proc = handle.process
    if proc is None or getattr(proc, "returncode", None) is not None:
        return False

    pid = proc.pid
    try:
        if sys.platform == "win32":
            return _kill_windows(pid)
        return _kill_posix(pid)
    except Exception:
        logger.exception("Failed to terminate run %s (pid %s)", handle.run_id, pid)
        return False
