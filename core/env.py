"""Load environment variables from the project .env file."""

import os
from pathlib import Path


def _repo_root() -> Path:
    """Return the repository root (parent of ``core/``)."""
    return Path(__file__).parent.parent


def load_env() -> None:
    """Read ``.env`` from the repo root and set values in ``os.environ``.

    Lines that are empty, start with ``#``, or lack an ``=`` are skipped.
    Already-set environment variables are never overwritten so that real
    shell exports take precedence.
    """
    env_path = _repo_root() / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value
