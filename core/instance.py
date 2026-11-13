"""One desktop app per user: the first launch owns it, later launches defer to it.

Without this, every launch of the packaged app started its own server on the
next free port and its own tray icon. Opening Scriptorium from the Start menu
while it sat in the tray left two of them running, and each further launch
added another. Worse, a second Chromium ``--app`` launch on the profile the
first one was using is handed to the running browser and exits at once, which
the launcher read as "the window was closed".

The rule is an exclusive lock on ``~/scriptorium/instance.lock``, held for the
life of the owning process. It is an OS file lock rather than a marker file, so
it disappears with the process however that process ends: a crash cannot leave
a stale lock that keeps the app from starting. The owner records its port next
to the lock; a later launch that cannot take the lock asks the owner, over that
port, to show its window, and exits.

On Windows the owner also holds a named mutex. Nothing here reads it — it is
what Inno Setup's ``AppMutex`` looks for, so the installer and uninstaller can
tell the app is running and ask the user to close it first.

Only the windowed launch takes part. A CLI invocation and the ``--run-script``
subprocesses the web UI spawns never touch the lock: several of those running
alongside the app is normal.
"""

import contextlib
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import IO
import urllib.request

logger = logging.getLogger(__name__)

#: Named mutex the owner holds on Windows; ``AppMutex`` in packaging/installer.iss.
MUTEX_NAME = "Scriptorium.SingleInstance"

#: The endpoint a later launch calls on the owner.
SHOW_PATH = "/api/show-window"

#: What the show endpoint answers with, so a later launch can tell it reached
#: Scriptorium and not some other program that took over a recorded port.
APP_ID = "scriptorium"

_LOCK_NAME = "instance.lock"
_RECORD_NAME = "instance.json"

# Let any process take the foreground. Granted by the launch the user just
# made — which Windows allows to set the foreground — so that the owner, a
# background process, may bring its window forward.
_ASFW_ANY = -1


def _data_dir() -> Path:
    from core.paths import _user_data_dir  # noqa: PLC0415

    return _user_data_dir()


def _lock_file(handle: IO) -> None:
    """Take a non-blocking exclusive lock on an open file.

    Args:
        handle: The open lock file.

    Raises:
        OSError: If another process already holds the lock.
    """
    if sys.platform == "win32":
        import msvcrt  # noqa: PLC0415

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl  # noqa: PLC0415

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _create_mutex() -> int | None:
    """Create the named mutex the installer checks for, on Windows.

    Returns:
        The mutex handle, or None elsewhere or on failure.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes  # noqa: PLC0415

        return ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME) or None
    except Exception:
        logger.warning("Could not create the %s mutex", MUTEX_NAME, exc_info=True)
        return None


@dataclass
class InstanceLock:
    """Proof that this process owns the desktop app.

    Attributes:
        handle: The open, locked lock file. Closing it releases the lock.
        data_dir: Where the lock and the port record live.
        mutex: Windows mutex handle for the installer, if one was created.
    """

    handle: IO
    data_dir: Path
    mutex: int | None = None

    def publish(self, port: int) -> None:
        """Record where this instance's server listens, for later launches.

        Args:
            port: The port the web server is bound to.
        """
        record = {"pid": os.getpid(), "port": port}
        (self.data_dir / _RECORD_NAME).write_text(json.dumps(record), encoding="utf-8")

    def release(self) -> None:
        """Give up ownership. The OS does this anyway when the process ends."""
        with contextlib.suppress(OSError):
            (self.data_dir / _RECORD_NAME).unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            self.handle.close()
        if self.mutex is not None:
            with contextlib.suppress(Exception):
                import ctypes  # noqa: PLC0415

                ctypes.windll.kernel32.CloseHandle(self.mutex)
            self.mutex = None


def acquire(data_dir: Path | None = None) -> InstanceLock | None:
    """Try to become the one running desktop app.

    Args:
        data_dir: Directory for the lock and record; ``~/scriptorium`` by default.

    Returns:
        The lock when this process now owns the app, or None when another
        process already does.
    """
    directory = data_dir or _data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    handle = open(directory / _LOCK_NAME, "a+", encoding="utf-8")  # noqa: SIM115 — held for the process lifetime
    try:
        _lock_file(handle)
    except OSError:
        handle.close()
        return None
    return InstanceLock(handle=handle, data_dir=directory, mutex=_create_mutex())


def _read_port(directory: Path) -> int | None:
    """Return the port the owner recorded, or None if there is no usable record."""
    try:
        record = json.loads((directory / _RECORD_NAME).read_text(encoding="utf-8"))
        return int(record["port"])
    except OSError, ValueError, KeyError, TypeError:
        return None


def _allow_foreground() -> None:
    """Let the owner bring its window to the front (Windows only)."""
    if sys.platform != "win32":
        return
    with contextlib.suppress(Exception):
        import ctypes  # noqa: PLC0415

        ctypes.windll.user32.AllowSetForegroundWindow(_ASFW_ANY)


def _ask(port: int, timeout: float) -> bool:
    """Ask the owner on *port* to show its window.

    Returns:
        True when Scriptorium answered and agreed.
    """
    request = urllib.request.Request(f"http://127.0.0.1:{port}{SHOW_PATH}", data=b"", method="POST")  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 — loopback only
            return json.loads(response.read().decode("utf-8")).get("app") == APP_ID
    except Exception:
        return False


def show_running_instance(data_dir: Path | None = None, wait: float = 10.0, poll: float = 0.25) -> bool:
    """Ask the app that owns the lock to bring its window forward.

    Retries for up to *wait* seconds, because the owner may have been launched
    a moment ago — a double-click on the shortcut does exactly that — and not
    have its server up, or its port recorded, yet.

    Args:
        data_dir: Directory holding the owner's record; ``~/scriptorium`` by default.
        wait: How long to keep trying, in seconds.
        poll: Pause between attempts, in seconds.

    Returns:
        True when the owner was reached and showed its window.
    """
    directory = data_dir or _data_dir()
    _allow_foreground()
    deadline = time.monotonic() + wait
    while True:
        port = _read_port(directory)
        if port is not None and _ask(port, timeout=2.0):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll)
