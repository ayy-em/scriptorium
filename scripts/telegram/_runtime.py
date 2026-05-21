"""Native-lib resolution shims that must run before WeasyPrint is imported.

On macOS, WeasyPrint dlopens pango/glib/cairo via ``cffi.FFI.dlopen(name)``
with bare library names like ``libgobject-2.0-0`` or ``libgobject-2.0.0.dylib``.
Homebrew installs those libraries under ``/opt/homebrew/lib`` (Apple Silicon)
or ``/usr/local/lib`` (Intel), neither of which is in macOS's default dlopen
search path. Setting ``DYLD_FALLBACK_LIBRARY_PATH`` after Python has launched
does not help because the dynamic linker reads it once at process start.

The fix here is to monkey-patch ``cffi.FFI.dlopen`` so that when the default
lookup fails, we retry with absolute paths under each known Homebrew prefix.
This is reversible, idempotent, and is a no-op on Linux/Windows (where the
default lookup already finds system libs).

When running from a frozen PyInstaller bundle, the bundled lib directory
(``sys._MEIPASS``) is also added to the fallback search list.
"""

import os
from pathlib import Path
import sys

_PATCHED = False

_MAC_BREW_LIB_PATHS = (
    "/opt/homebrew/lib",  # Apple Silicon
    "/usr/local/lib",  # Intel Mac
)


def ensure_native_lib_resolution() -> None:
    """Install the cffi dlopen fallback patch. Safe to call multiple times."""
    global _PATCHED  # noqa: PLW0603 — module-level idempotency guard
    if _PATCHED:
        return
    _PATCHED = True

    search_paths = _candidate_lib_paths()
    if not search_paths:
        return

    import cffi  # noqa: PLC0415 — local import so non-telegram callers don't pay for it

    _original_dlopen = cffi.FFI.dlopen

    def _patched(self, name, flags=0):  # type: ignore[no-untyped-def]
        try:
            return _original_dlopen(self, name, flags)
        except OSError:
            if name.startswith("/"):
                raise
            for prefix in search_paths:
                full = os.path.join(prefix, name)
                if os.path.exists(full):
                    return _original_dlopen(self, full, flags)
            raise

    cffi.FFI.dlopen = _patched  # type: ignore[method-assign]


def _candidate_lib_paths() -> tuple[str, ...]:
    """Return directories to search for native libs, in priority order."""
    candidates: list[str] = []

    # Frozen PyInstaller bundle: native libs are bundled alongside Python modules.
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        bundled_lib = Path(bundle) / "lib"
        if bundled_lib.is_dir():
            candidates.append(str(bundled_lib))

    if sys.platform == "darwin":
        for p in _MAC_BREW_LIB_PATHS:
            if os.path.isdir(p):
                candidates.append(p)

    return tuple(candidates)
