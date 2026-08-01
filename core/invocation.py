"""Who started this run — the web UI, or a human at a terminal.

The two want opposite things from a relative path. The web UI uploads into
``inputs/`` and reads results out of ``outputs/``, so a bare filename means "the
file I just staged" and a missing ``--output`` means "somewhere the UI can find
it". A person typing ``scriptorium av.trim clip.mp4`` in a directory full of
video means the file in front of them, and expects the result beside it.

Both callers reach a script through the same ``argv``, so the difference cannot
be inferred at the point of resolution — the webapp announces itself instead.
An environment variable rather than a flag, because the two spawn paths do not
share an argv shape: frozen runs go through ``--run-script``, development runs
are ``python main.py <key>``, which is exactly what a human types.
"""

import os

CALLER_ENV_VAR = "SCRIPTORIUM_CALLER"
_WEBAPP = "webapp"


def webapp_spawn_env() -> dict[str, str]:
    """Return the environment a script subprocess spawned by the webapp needs.

    Returns:
        A copy of the current environment marked as a webapp-initiated run,
        suitable for passing as ``env=`` to a subprocess call.
    """
    return {**os.environ, CALLER_ENV_VAR: _WEBAPP}


def is_webapp_run() -> bool:
    """Report whether this process was started by the web UI.

    Returns:
        True when the webapp spawned this run, False for a human CLI
        invocation.
    """
    return os.environ.get(CALLER_ENV_VAR) == _WEBAPP
