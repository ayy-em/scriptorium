"""Crop a photo to a box drawn on it in the web UI."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

from PIL import Image

from core.argparse import ScriptoriumParser
from core.images import open_upright
from core.outputs import resolve_output
from core.paths import resolve_input

TITLE = "Crop a photo"
DESCRIPTION = "Drag a box over a picture and keep just that part."
ACCEPTS: set[str] = {"image"}
TEMPLATE = "scripts/photo/crop.html"

# The interface is the box drawn on the picture. The flags below exist so a
# run can be recorded and re-run from History, not as a command line anyone
# is expected to type — see "Optional: UI_ONLY" in SPEC.md.
UI_ONLY = True

_THEME = "photo"

FORMAT_SAME = "same"
FORMATS = (FORMAT_SAME, "png", "jpg", "webp")

# What "same" becomes when the source format cannot be written back. Pillow
# reads HEIC through pillow-heif but the app does not encode it, and a few
# read-only formats exist besides.
_FALLBACK_EXT = ".jpg"

# Formats this script writes, by extension. Anything else under "same" falls
# back to JPEG.
_WRITABLE = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP", ".gif": "GIF", ".bmp": "BMP"}
_WRITABLE |= {".tif": "TIFF", ".tiff": "TIFF"}
_LOSSY = frozenset({"JPEG", "WEBP"})
_NO_ALPHA = frozenset({"JPEG", "BMP"})

DEFAULT_QUALITY = 95


class CropError(ValueError):
    """The requested box cannot be cut from this image."""


@dataclass(frozen=True)
class Box:
    """A crop rectangle in pixels of the upright image.

    Attributes:
        x: Left edge.
        y: Top edge.
        width: Width in pixels.
        height: Height in pixels.
    """

    x: int
    y: int
    width: int
    height: int

    def as_pillow(self) -> tuple[int, int, int, int]:
        """Return the (left, upper, right, lower) tuple ``Image.crop`` takes."""
        return (self.x, self.y, self.x + self.width, self.y + self.height)


def check_box(box: Box, size: tuple[int, int]) -> None:
    """Refuse a box that is empty or reaches outside the image.

    Args:
        box: The requested crop.
        size: (width, height) of the upright image.

    Raises:
        CropError: Naming what is wrong with the box.
    """
    width, height = size
    if box.width <= 0 or box.height <= 0:
        raise CropError(f"The crop box must have a size; got {box.width}×{box.height}.")
    if box.x < 0 or box.y < 0 or box.x + box.width > width or box.y + box.height > height:
        raise CropError(
            f"The crop box {box.width}×{box.height} at ({box.x}, {box.y}) does not fit "
            f"inside the {width}×{height} image."
        )


def output_ext(source: Path, fmt: str) -> tuple[str, str | None]:
    """Choose the output extension for a source file and a --format choice.

    Args:
        source: The input image.
        fmt: One of ``FORMATS``.

    Returns:
        ``(ext, note)`` — the extension with its dot, and a sentence to print
        when "same" could not be honoured, else None.
    """
    if fmt != FORMAT_SAME:
        return f".{fmt}", None
    ext = source.suffix.lower()
    if ext in _WRITABLE:
        return ext, None
    return _FALLBACK_EXT, f"{source.suffix or 'This format'} cannot be written back, so the crop is saved as JPEG."


def _save_kwargs(image: Image.Image, pillow_format: str, quality: int) -> dict:
    kwargs: dict = {}
    # Keep the colour profile: an iPhone photo is Display P3, and dropping its
    # profile makes the crop look duller than the photo it came from.
    icc = image.info.get("icc_profile")
    if icc:
        kwargs["icc_profile"] = icc
    if pillow_format in _LOSSY:
        kwargs["quality"] = quality
    return kwargs


def crop(source: Path, box: Box, output: Path, *, quality: int = DEFAULT_QUALITY) -> Path:
    """Cut *box* out of *source* and write it to *output*.

    Args:
        source: Image to crop.
        box: Region to keep, in pixels of the upright image.
        output: Destination file; its extension picks the format.
        quality: JPEG/WebP quality, 1–95. Ignored for lossless formats.

    Returns:
        The written path.

    Raises:
        CropError: When the box does not fit the image.
    """
    image = open_upright(source)
    check_box(box, image.size)
    cropped = image.crop(box.as_pillow())
    pillow_format = _WRITABLE.get(output.suffix.lower(), "JPEG")
    if pillow_format in _NO_ALPHA and cropped.mode not in {"RGB", "L"}:
        cropped = cropped.convert("RGB")
    cropped.save(output, format=pillow_format, **_save_kwargs(image, pillow_format, quality))
    return output


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = ScriptoriumParser(description=DESCRIPTION, prog="uv run main.py photo.crop")
    parser.add_argument("input", type=Path, help="Image to crop")
    parser.add_argument("--x", type=int, required=True, ui_label="Left", help="Left edge of the box, in pixels")
    parser.add_argument("--y", type=int, required=True, ui_label="Top", help="Top edge of the box, in pixels")
    parser.add_argument("--width", type=int, required=True, ui_label="Width", help="Box width, in pixels")
    parser.add_argument("--height", type=int, required=True, ui_label="Height", help="Box height, in pixels")
    parser.add_argument(
        "--format",
        default=FORMAT_SAME,
        choices=FORMATS,
        ui_label="Format",
        help="Output format; same keeps the input's (HEIC is saved as JPEG)",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=DEFAULT_QUALITY,
        ui_label="Quality",
        ui_advanced=True,
        help="JPEG and WebP quality, 1–95 (default: 95)",
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
    """Entrypoint for a run the web UI started."""
    args = get_parser().parse_args()
    source = resolve_input(args.input, _THEME)
    box = Box(args.x, args.y, args.width, args.height)
    ext, note = output_ext(source, args.format)
    if note:
        print(note, file=sys.stderr)
    output = resolve_output(args.output, theme=_THEME, ext=ext)
    try:
        crop(source, box, output, quality=max(1, min(95, args.quality)))
    except CropError as e:
        output.unlink(missing_ok=True)
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    # The input stays in inputs/: cropping the same photo again, with a
    # different box, is the common next step. See "Which scripts archive".
    print(output)
