"""Archive every scripts/*/inputs/ and scripts/*/outputs/ tree into a timestamped snapshot."""

import argparse
from datetime import datetime
from pathlib import Path
import sys

TITLE = "Archive inputs and outputs"
DESCRIPTION = "Sweep scripts/*/inputs/ and scripts/*/outputs/ into a timestamped archive/ snapshot."

_TARGET_DIRS = ("inputs", "outputs")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _collect_moves(scripts_root: Path, archive_dir: Path) -> list[tuple[Path, Path]]:
    moves: list[tuple[Path, Path]] = []
    for name in _TARGET_DIRS:
        for directory in scripts_root.rglob(name):
            if not directory.is_dir():
                continue
            for file in directory.rglob("*"):
                if file.is_file():
                    moves.append((file, archive_dir / file.relative_to(scripts_root)))
    return sorted(moves)


def cleanup(scripts_root: Path, archive_dir: Path, *, dry_run: bool) -> int:
    """Move every file inside scripts/<theme>/inputs|outputs/ into archive_dir.

    Returns the number of files moved (or that would be moved in dry-run mode).
    """
    moves = _collect_moves(scripts_root, archive_dir)
    if not moves:
        print("nothing to archive.")
        return 0

    verb = "would move" if dry_run else "move"
    archive_root = archive_dir.parent
    for src, dst in moves:
        print(f"  {verb}  {src.relative_to(scripts_root)}  →  {dst.relative_to(archive_root)}")

    if dry_run:
        print(f"\ndry run: {len(moves)} file(s) pending. pass --apply to execute.")
        return len(moves)

    for src, dst in moves:
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
    print(f"\n{len(moves)} file(s) archived to {archive_dir}.")
    return len(moves)


_EXAMPLES = """
examples:
  uv run main.py util.cleanup                # dry-run preview
  uv run main.py util.cleanup --apply        # actually archive
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py util.cleanup",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually move files (default is dry-run preview)",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to cleanup()."""
    args = get_parser().parse_args()
    repo_root = _repo_root()
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    cleanup(repo_root / "scripts", repo_root / "archive" / timestamp, dry_run=not args.apply)
    sys.exit(0)
