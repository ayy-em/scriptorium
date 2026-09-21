"""Centralized path resolution for frozen (PyInstaller) and development modes."""

from datetime import datetime
from pathlib import Path
import shutil
import sys
import tomllib

from core.invocation import is_webapp_run

FROZEN = getattr(sys, "frozen", False)


def _bundle_dir() -> Path:
    """Root of the PyInstaller bundle, or the repo root in development."""
    if FROZEN:
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).parent.parent


def _user_data_dir() -> Path:
    """Return ~/scriptorium/ — user-facing data directory for the packaged app."""
    return Path.home() / "scriptorium"


def templates_dir() -> Path:
    """Return the Jinja2 templates directory."""
    return _bundle_dir() / "webapp" / "templates"


def static_dir() -> Path:
    """Return the static assets directory."""
    return _bundle_dir() / "webapp" / "static"


def assets_dir() -> Path:
    """Return the shared assets directory (fonts, images used across themes)."""
    return _bundle_dir() / "assets"


def inputs_dir(theme: str) -> Path:  # noqa: ARG001
    """Return the shared inputs directory, creating it if needed.

    Theme argument is preserved for API compatibility but ignored: every script
    reads from the same root inputs directory.
    """
    d = _user_data_dir() / "inputs" if FROZEN else _bundle_dir() / "inputs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_input(source: Path, theme: str) -> Path:
    """Resolve a user-supplied input path for whoever supplied it.

    ``~`` is expanded first: nothing typed into the web UI passes through a
    shell, so an unexpanded tilde would be read as a directory of that literal
    name sitting next to the server.

    A bare filename is the ambiguous case. From the web UI it names a file
    staged in ``inputs/``; from a terminal it names a file in the current
    directory, the way every other command-line tool behaves. A relative path
    *with* a directory part is measured against the home directory under the web
    UI and against the current directory on the command line, matching
    ``core.outputs.anchor_user_path``. Absolute paths are returned untouched.

    ``./name`` is *not* a way to force the cwd: ``Path`` normalises the leading
    ``./`` away at construction, so it arrives here identical to ``name``. That
    costs nothing in practice — the web UI passes absolute paths (the upload
    endpoint returns one), so its bare-filename branch only ever serves a human
    who put a file in ``inputs/`` and typed its name.

    Args:
        source: Path exactly as the caller supplied it.
        theme: Script theme slug, for the inputs directory lookup.

    Returns:
        The path to actually read from.
    """
    from core.outputs import relative_root  # noqa: PLC0415

    source = source.expanduser()
    if source.is_absolute():
        return source
    if source.parent != Path("."):
        return relative_root() / source
    if is_webapp_run():
        return inputs_dir(theme) / source.name
    return source


def drop_session_dir(session_id: str) -> Path:
    """Return an isolated directory for one drag-drop or paste session.

    Lives at ``inputs/drop/<session_id>/`` so that directory-native scripts run
    against exactly the files just dropped, without picking up unrelated files
    sitting in the shared inputs root.

    Args:
        session_id: Filesystem-safe identifier for this drop.

    Returns:
        The created session directory.
    """
    d = inputs_dir("drop") / "drop" / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def past_inputs_dir(theme: str) -> Path:  # noqa: ARG001
    """Return the processed-inputs archive directory, creating it if needed.

    Lives at ``inputs/processed/`` so users can see archived files alongside
    their unprocessed ones. Theme argument preserved for API compatibility.
    """
    d = inputs_dir(theme) / "processed"
    d.mkdir(parents=True, exist_ok=True)
    return d


def move_to_past_inputs(theme: str, source: Path) -> Path | None:
    """Move a processed input file to ``inputs/processed/``.

    This is the only sanctioned way to archive an input, and the guard is the
    reason: a file is moved **only** when it lives inside the shared inputs
    root. Point a script at ``~/Movies/holiday.mp4`` and it is read and left
    exactly where it was; stage a file in ``inputs/`` and it is filed away once
    it has been used. Scripts that rolled their own ``processed/`` directory
    created one next to whatever the user pointed at, which made pointing a
    script at a real media library a destructive act.

    Files already inside ``processed/`` are skipped, so re-running against the
    archive does not shuffle it.

    Args:
        theme: Script theme slug, for the inputs directory lookup.
        source: File the run has finished with.

    Returns:
        The destination path, or ``None`` when the source was skipped (outside
        the inputs root, already archived, not a file) or the move failed.
        Callers ignore the return value: failing to tidy up is never a reason
        to fail a run that already produced its output.
    """
    if not source.is_file():
        return None
    try:
        source_resolved = source.resolve()
        inputs_root = inputs_dir(theme).resolve()
        past_root = past_inputs_dir(theme).resolve()
    except OSError:
        return None
    try:
        source_resolved.relative_to(inputs_root)
    except ValueError:
        return None
    if source_resolved.is_relative_to(past_root):
        return None

    dest = past_root / source.name
    if dest.exists():
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        dest = past_root / f"{source.stem}_{stamp}{source.suffix}"
    try:
        shutil.move(str(source), str(dest))
    except OSError:
        return None
    return dest


def logs_dir() -> Path:
    """Return the directory for runtime logs, creating it if needed."""
    if FROZEN:
        d = _user_data_dir() / "logs"
    else:
        d = _bundle_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def outputs_root() -> Path:
    """Return the root outputs directory, creating it if needed.

    Unlike outputs_dir(), no theme subdirectory is appended. Used by the
    "open outputs folder" button, which reveals every theme's results at once
    rather than guessing at one.

    Returns:
        The outputs root — the user's configured directory if set, otherwise
        the default location for this install.
    """
    from core.config import load as _load_config  # noqa: PLC0415

    custom = _load_config().outputs_dir
    if custom:
        d = Path(custom)
    elif FROZEN:
        d = _user_data_dir() / "outputs"
    else:
        d = _bundle_dir() / "outputs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def outputs_dir(theme: str) -> Path:
    """Return the outputs directory for a theme, creating it if needed.

    If the user has set a custom outputs directory in settings, it is used
    as the root (with a theme subdirectory). Otherwise the default location
    is used.
    """
    d = outputs_root() / theme
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_version() -> str:
    """Read the project version, with frozen-mode fallback."""
    try:
        with open(_bundle_dir() / "pyproject.toml", "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except Exception:
        return "—"
