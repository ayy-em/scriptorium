"""Make a script process's output writable whatever it contains.

Python picks stdout's encoding from where the stream goes. A Windows console
gets UTF-8, but a pipe or a file gets the ANSI code page — cp1252 on a Western
install — with ``errors="strict"``. That code page has no ``→`` and no
Cyrillic, so a script that printed either crashed with ``UnicodeEncodeError``
as soon as its output was piped. The web UI runs every script on a pipe, so
there it was not an edge case: ``av.join`` printing "trailing black … →
trimmed" was enough to fail a join part-way through. Short of
crashing, the bytes were still wrong: the web UI decodes a script's output as
UTF-8.

So the two kinds of reader get different fixes:

- **The web UI** reads UTF-8, so a process it spawned writes UTF-8.
- **A person piping or redirecting** keeps the encoding their shell expects;
  what that encoding cannot hold becomes ``?`` instead of a traceback.
"""

import sys
from typing import TextIO

from core.invocation import is_webapp_run


def _reconfigure(stream: TextIO | None, **kwargs: str) -> None:
    # A windowed build may have no stream at all, or a stand-in without
    # reconfigure(); neither has anything to fix.
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(**kwargs)
    except AttributeError, ValueError, OSError:
        pass


def configure() -> None:
    """Set stdout and stderr up so no character can crash a write.

    Call once, early, in a process that is about to run a script or print a
    listing.
    """
    if is_webapp_run():
        settings = {"encoding": "utf-8", "errors": "replace"}
    else:
        settings = {"errors": "replace"}
    _reconfigure(sys.stdout, **settings)
    _reconfigure(sys.stderr, **settings)
