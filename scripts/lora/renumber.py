"""LoRA dataset image renumbering script."""

import argparse
from pathlib import Path
import sys

from core.paths import inputs_dir
from scripts.lora._dataset import find_images

TITLE = "Renumber LoRA dataset images"
DESCRIPTION = "Rename all images (and paired captions) to sequential img_001, img_002, ... naming."


def _inputs() -> Path:
    return inputs_dir("lora")


def renumber(directory: Path, *, dry_run: bool) -> None:
    """Rename images in directory to sequential img_NNN naming."""
    if not directory.is_dir():
        print(f"error: inputs directory not found: {directory}", file=sys.stderr)
        sys.exit(1)

    images = find_images(directory)
    if not images:
        print("no images found.")
        return

    width = max(3, len(str(len(images))))
    renames: list[tuple[Path, Path]] = []

    for i, img in enumerate(images, start=1):
        stem = f"img_{i:0{width}d}"
        new_img = directory / f"{stem}{img.suffix.lower()}"
        if new_img != img:
            renames.append((img, new_img))
        old_cap = directory / f"{img.stem}.txt"
        new_cap = directory / f"{stem}.txt"
        if old_cap.exists() and new_cap != old_cap:
            renames.append((old_cap, new_cap))

    if not renames:
        print("already correctly numbered, nothing to do.")
        return

    for src, dst in renames:
        print(f"  {'would rename' if dry_run else 'rename'}  {src.name}  →  {dst.name}")

    if dry_run:
        print(f"\ndry run: {len(renames)} rename(s) pending. pass --apply to execute.")
        return

    for src, dst in renames:
        src.rename(dst)
    print(f"\n{len(renames)} file(s) renamed.")


_EXAMPLES = """
examples:
  uv run main.py lora.renumber                              # dry-run preview
  uv run main.py lora.renumber --apply
  uv run main.py lora.renumber --inputs path/to/dataset/ --apply
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py lora.renumber",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--inputs",
        type=Path,
        default=None,
        metavar="DIR",
        help="dataset directory (default: lora/inputs/; bare name resolves to lora/inputs/)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually rename files (default is dry-run preview)",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to renumber()."""
    args = get_parser().parse_args()
    inputs = args.inputs or _inputs()
    if inputs.parent == Path("."):
        inputs = _inputs() / inputs.name
    renumber(inputs, dry_run=not args.apply)
