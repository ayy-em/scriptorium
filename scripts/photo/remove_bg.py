"""Remove background from images, producing PNGs with alpha transparency."""

import argparse
from pathlib import Path
import sys

from PIL import Image

from core.argparse import ScriptoriumParser
from core.outputs import deduplicate, default_stem, resolve_output, resolve_output_dir
from scripts.formats._utils import IMAGE_EXTS, find_files

TITLE = "Remove background"
DESCRIPTION = "Remove image backgrounds using AI, outputting transparent PNGs."
ACCEPTS: set[str] = {"image"}

_THEME = "photo"


def remove_bg(source: Path, output: Path) -> None:
    """Remove the background from a single image and save as PNG.

    Args:
        source: Path to the input image.
        output: Path for the output PNG file.
    """
    from rembg import remove  # noqa: PLC0415

    img = Image.open(source)
    result = remove(img)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output, format="PNG")


def remove_bg_batch(source: Path, outputs_dir: Path) -> list[Path]:
    """Remove backgrounds from a single image or all images in a directory.

    Args:
        source: Source image file or directory of images.
        outputs_dir: Directory where output PNGs are written.

    Returns:
        List of successfully created output paths.

    Raises:
        FileNotFoundError: If the source path does not exist.
        RuntimeError: If any files fail in batch mode.
    """
    if not source.exists():
        raise FileNotFoundError(f"source not found: {source}")

    outputs_dir.mkdir(parents=True, exist_ok=True)
    stamp = default_stem()

    if source.is_file():
        output = deduplicate(outputs_dir / f"{stamp}.png")
        remove_bg(source, output)
        return [output]

    files = find_files(source, IMAGE_EXTS)
    if not files:
        return []

    successes: list[Path] = []
    failures: list[str] = []

    for i, f in enumerate(files, 1):
        output = outputs_dir / f"{stamp}_{i:03d}.png"
        try:
            remove_bg(f, output)
            successes.append(output)
        except Exception as e:
            failures.append(f"{f.name}: {e}")

    if failures:
        bullet_list = "\n".join(f"  - {msg}" for msg in failures)
        raise RuntimeError(f"{len(failures)} of {len(files)} file(s) failed:\n{bullet_list}")

    return successes


_EXAMPLES = """
examples:
  uv run main.py photo.remove_bg portrait.jpg
  uv run main.py photo.remove_bg photos/ -o cleaned/
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = ScriptoriumParser(
        description=DESCRIPTION,
        prog="uv run main.py photo.remove_bg",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Source image file or directory of images",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        metavar="PATH",
        help="Output file or directory (default: outputs/photo/)",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to remove_bg_batch()."""
    args = get_parser().parse_args()

    if args.source.is_file():
        out = resolve_output(args.output, theme=_THEME, ext=".png")
        try:
            remove_bg(args.source, out)
            print(out)
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        out_dir = resolve_output_dir(args.output, theme=_THEME)
        try:
            outputs = remove_bg_batch(args.source, out_dir)
            for o in outputs:
                print(o)
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(1)
