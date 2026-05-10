"""CLI entrypoint for scriptorium — lists and dispatches themed utility scripts."""

import sys

from core.registry import discover
from core.runner import run

_MIN_ARGS = 2


def main() -> None:
    """Parse the script key from argv and dispatch, or list all available scripts."""
    if len(sys.argv) < _MIN_ARGS:
        _list()
        return
    run(sys.argv[1])


def _list() -> None:
    scripts = discover()
    if not scripts:
        print("No scripts found.")
        return
    for key, mod in sorted(scripts.items()):
        print(f"  {key:<40}  {mod.TITLE}")


if __name__ == "__main__":
    main()
