"""Record the commit a frozen build was made from.

The web UI shows the short git hash next to the version in the sidebar. In
development it comes from ``git rev-parse`` at startup, but a packaged app has
no repository to ask — the install directory is a PyInstaller bundle — so the
hash showed as "—" in every Windows and macOS build. The spec files call
:func:`write_build_sha` while they run, which is the one moment the repository
is still in reach, and bundle the resulting file next to ``pyproject.toml`` for
``core.paths.read_build_sha`` to pick up.
"""

import os
from pathlib import Path
import subprocess

BUILD_SHA_FILENAME = "build_sha.txt"
_SHORT_SHA_LENGTH = 7


def build_sha(root: Path) -> str:
    """Return the short hash of the commit being built.

    Asks git first. CI checkouts are shallow but still answer that. When there
    is no git at all — a source tarball — ``GITHUB_SHA`` is the fallback, which
    Actions sets for every job.

    Args:
        root: Repository root to run git in.

    Returns:
        A short hash, or an empty string when neither source knows one.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:  # noqa: S110 - any failure means "ask the environment instead"
        pass
    return os.environ.get("GITHUB_SHA", "").strip()[:_SHORT_SHA_LENGTH]


def write_build_sha(root: Path, dest_dir: Path) -> Path:
    """Write the build's commit hash to a file PyInstaller can bundle.

    Written even when the hash is unknown, so the spec's ``datas`` entry
    always points at a file that exists and a build never fails over it.

    Args:
        root: Repository root to run git in.
        dest_dir: Directory to write into; created if missing.

    Returns:
        The path of the written file.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / BUILD_SHA_FILENAME
    path.write_text(build_sha(root) + "\n", encoding="utf-8")
    return path
