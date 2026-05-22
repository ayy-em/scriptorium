"""Centralized path resolution for frozen (PyInstaller) and development modes."""

from datetime import datetime
from pathlib import Path
import shutil
import sys
import tomllib

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

    Only moves files that live inside the shared inputs root — files passed via
    an absolute path outside that tree (or already inside ``processed/``) are
    left alone. Returns the destination path on success, ``None`` if the source
    was skipped or the move failed.

    Filename collisions inside ``processed/`` are resolved by appending a
    timestamp suffix so prior archived copies are preserved.
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


def outputs_dir(theme: str) -> Path:
    """Return the outputs directory for a theme, creating it if needed.

    If the user has set a custom outputs directory in settings, it is used
    as the root (with a theme subdirectory). Otherwise the default location
    is used.
    """
    from core.config import load as _load_config  # noqa: PLC0415

    custom = _load_config().outputs_dir
    if custom:
        d = Path(custom) / theme
    elif FROZEN:
        d = _user_data_dir() / "outputs" / theme
    else:
        d = _bundle_dir() / "outputs" / theme
    d.mkdir(parents=True, exist_ok=True)
    return d


def has_ffmpeg() -> bool:
    """Return True if ffmpeg is available on PATH."""
    return shutil.which("ffmpeg") is not None


def read_version() -> str:
    """Read the project version, with frozen-mode fallback."""
    try:
        with open(_bundle_dir() / "pyproject.toml", "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except Exception:
        return "—"
