"""Environment variables from ``.env`` files, and the one the app can write.

Two files are read, in order: the repo-root ``.env`` a developer keeps, then
the user's own ``~/scriptorium/.env``. The second exists so the packaged app
has somewhere it may write: its install directory is not writable, and a key
typed into the settings modal has to land somewhere that survives an upgrade.
Real shell exports beat both files.
"""

import os
from pathlib import Path
import sys


def _repo_root() -> Path:
    """Return the repository root (parent of ``core/``)."""
    return Path(__file__).parent.parent


def user_env_path() -> Path:
    """Return the ``.env`` the app itself writes, next to ``config.json``.

    Returns:
        ``~/scriptorium/.env``, which may not exist yet.
    """
    return Path.home() / "scriptorium" / ".env"


def _parse(text: str) -> dict[str, str]:
    """Read ``KEY=value`` lines, ignoring comments, blanks and quotes.

    Args:
        text: Contents of a ``.env`` file.

    Returns:
        Mapping of key to unquoted value, last occurrence winning.
    """
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key:
            values[key] = value.strip().strip("\"'")
    return values


def _apply(path: Path) -> None:
    """Load one file into ``os.environ`` without overwriting what is set.

    Args:
        path: A ``.env`` file; silently skipped when absent.
    """
    if not path.is_file():
        return
    for key, value in _parse(path.read_text(encoding="utf-8")).items():
        if key not in os.environ:
            os.environ[key] = value


def load_env() -> None:
    """Read the repo ``.env`` and then the user ``.env`` into ``os.environ``.

    Already-set environment variables are never overwritten so that real
    shell exports take precedence, and the repo file wins over the user one.
    """
    _apply(_repo_root() / ".env")
    _apply(user_env_path())


def _write_user_env(values: dict[str, str]) -> None:
    """Rewrite the user ``.env`` with the given values, readable by the owner only.

    Args:
        values: The complete set of keys the file should hold.
    """
    path = user_env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{key}={value}\n" for key, value in values.items())
    path.write_text(body, encoding="utf-8")
    if sys.platform != "win32":
        path.chmod(0o600)


def set_env_value(key: str, value: str) -> None:
    """Store a value in the user ``.env`` and in this process.

    The process is updated too, so a probe that reads ``os.environ`` sees the
    change without a restart. An empty value removes the key instead: there
    is no meaningful difference between "set to nothing" and "not set".

    Args:
        key: Variable name, e.g. ``"OPENAI_API_KEY"``.
        value: Its value; empty to remove it.
    """
    value = value.strip()
    path = user_env_path()
    values = _parse(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if value:
        values[key] = value
        os.environ[key] = value
    else:
        values.pop(key, None)
        os.environ.pop(key, None)
    _write_user_env(values)
