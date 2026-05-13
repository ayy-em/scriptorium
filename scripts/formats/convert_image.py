"""CLI and programmatic interface for converting image files between formats."""

import argparse
from pathlib import Path
import sys

from PIL import Image

from scripts.formats._utils import (
    IMAGE_EXTS,
    BatchConvertError,
    formats_inputs_dir,
    formats_outputs_dir,
    run_convert,
)

TITLE = "Convert image"
DESCRIPTION = "Convert images to a different format using Pillow."

_IMAGE_OUT_FORMATS = ["jpg", "png", "webp", "gif", "bmp", "tiff"]
_QUALITY_EXTS = frozenset({".jpg", ".jpeg", ".webp"})
_NEEDS_RGB = frozenset({".jpg", ".jpeg"})


def _convert(input_path: Path, output: Path, quality: int) -> None:
    """Open an image and save it in the target format.

    Args:
        input_path: Source image file.
        output: Destination image file.
        quality: JPEG/WebP quality (1–100). Ignored for lossless formats.
    """
    img = Image.open(input_path)
    if output.suffix.lower() in _NEEDS_RGB and img.mode in {"RGBA", "LA", "P"}:
        img = img.convert("RGB")
    kwargs = {"quality": quality} if output.suffix.lower() in _QUALITY_EXTS else {}
    img.save(output, **kwargs)


def convert(
    source: Path,
    to_format: str,
    outputs_dir: Path,
    *,
    quality: int = 85,
) -> list[Path]:
    """Convert a single image or a directory of images to a target format.

    Args:
        source: Source image file or directory of image files.
        to_format: Target format extension without leading dot (e.g. "jpg", "webp").
        outputs_dir: Directory where converted files are written.
        quality: Output quality 1–100 for JPEG/WebP (default: 85). Ignored for other formats.

    Returns:
        List of successfully created output Paths.

    Raises:
        subprocess.CalledProcessError: If Pillow fails in single-file mode.
        BatchConvertError: If any files fail in batch mode (after processing all).
    """

    def _fn(inp: Path, out: Path) -> None:
        _convert(inp, out, quality)

    return run_convert(source, IMAGE_EXTS, outputs_dir, to_format, _fn)


_EXAMPLES = """
examples:
  uv run main.py formats.convert_image photo.png --to webp
  uv run main.py formats.convert_image --to jpg --quality 90
  uv run main.py formats.convert_image scans/ --to png
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py formats.convert_image",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source",
        type=Path,
        nargs="?",
        help="Source file or directory (default: formats/inputs/)",
    )
    parser.add_argument(
        "--to",
        required=True,
        dest="to_format",
        metavar="FORMAT",
        choices=_IMAGE_OUT_FORMATS,
        help="Target format",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=85,
        metavar="1-100",
        help="Output quality for JPEG/WebP (default: 85). Ignored for other formats.",
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        default=None,
        metavar="DIR",
        help="Output directory (default: formats/outputs/)",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to convert()."""
    args = get_parser().parse_args()
    source = args.source or formats_inputs_dir()
    out_dir = args.outputs or formats_outputs_dir()

    try:
        outputs = convert(source, args.to_format, out_dir, quality=args.quality)
        for o in outputs:
            print(o)
        sys.exit(0)
    except BatchConvertError as e:
        for o in e.succeeded:
            print(o)
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
