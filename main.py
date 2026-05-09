import sys

from core.registry import discover
from core.runner import run


def main() -> None:
    if len(sys.argv) < 2:
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
