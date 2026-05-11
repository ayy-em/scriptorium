"""CLI entrypoint for scriptorium — lists and dispatches themed utility scripts."""

import sys

from core.registry import discover, discover_themes
from core.runner import run

_MIN_ARGS = 2


def main() -> None:
    """Parse the script key from argv and dispatch, or list all available scripts."""
    if len(sys.argv) < _MIN_ARGS:
        _list()
        return

    first = sys.argv[1]

    # Bare theme name (with or without a trailing --help): show section listing.
    if "." not in first and not first.startswith("-"):
        _list_theme(first)
        return

    run(first)


def _list() -> None:
    scripts = discover()
    if not scripts:
        print("No scripts found.")
        return
    for key, mod in sorted(scripts.items()):
        print(f"  {key:<40}  {mod.TITLE}")


def _list_theme(theme: str) -> None:
    all_themes = discover_themes()
    if theme not in all_themes:
        available = ", ".join(sorted(all_themes))
        print(f"Unknown theme '{theme}'. Available: {available}", file=sys.stderr)
        sys.exit(1)
    scripts = all_themes[theme]
    print(f"Theme '{theme}' ({len(scripts)} script(s)):\n")
    for name, mod in sorted(scripts.items()):
        key = f"{theme}.{name}"
        print(f"  {key:<40}  {mod.TITLE}")
        print(f"  {'':40}  {mod.DESCRIPTION}")
        print()
    print(f"Run 'uv run main.py {theme}.<script> --help' for usage details.")


if __name__ == "__main__":
    main()
