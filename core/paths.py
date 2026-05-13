"""Centralized path resolution for frozen (PyInstaller) and development modes."""

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


def inputs_dir(theme: str) -> Path:
    """Return the inputs directory for a theme, creating it if needed."""
    if FROZEN:
        d = _user_data_dir() / "inputs" / theme
    else:
        d = _bundle_dir() / "scripts" / theme / "inputs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def outputs_dir(theme: str) -> Path:
    """Return the outputs directory for a theme, creating it if needed."""
    if FROZEN:
        d = _user_data_dir() / "outputs" / theme
    else:
        d = _bundle_dir() / "scripts" / theme / "outputs"
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
