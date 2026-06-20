"""Build an animated GIF from a folder of sequentially named images."""

import argparse
from pathlib import Path
import sys

from core.argparse import ScriptoriumParser
from core.outputs import resolve_output
from core.paths import inputs_dir

TITLE = "Make a gif"
DESCRIPTION = "Takes a folder full of sequentially named pics, creates a gif."

_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif"})


def _inputs() -> Path:
    return inputs_dir("gif")


def _find_frames(directory: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in _IMAGE_EXTS)


def generate(
    source: Path,
    output: Path,
    *,
    fps: int = 12,
    width: int | None = None,
    loop: int = 0,
) -> Path:
    """Compose a single animated GIF from every image found in ``source``.

    Args:
        source: Directory of frames. Filenames are sorted lexically so
            ``frame_001.png`` precedes ``frame_002.png``.
        output: Destination .gif path.
        fps: Frames per second (positive integer). Defaults to 12.
        width: Optional resize width in pixels; aspect ratio is preserved.
            ``None`` keeps the source resolution.
        loop: Loop count for the GIF (``0`` means infinite). Defaults to 0.

    Returns:
        The output path on success.

    Raises:
        FileNotFoundError: If ``source`` is not a directory or contains no images.
        ValueError: If ``fps`` is not positive or ``width`` is non-positive.
    """
    if not source.is_dir():
        raise FileNotFoundError(f"source directory not found: {source}")
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    if width is not None and width <= 0:
        raise ValueError(f"width must be positive when set, got {width}")

    from PIL import Image  # noqa: PLC0415

    frame_paths = _find_frames(source)
    if not frame_paths:
        raise FileNotFoundError(f"no images found in {source}")

    frames: list[Image.Image] = []
    for path in frame_paths:
        img = Image.open(path).convert("RGBA")
        if width is not None and width != img.width:
            ratio = width / img.width
            new_size = (width, max(1, int(round(img.height * ratio))))
            img = img.resize(new_size, Image.LANCZOS)
        frames.append(img)

    duration_ms = max(1, int(round(1000 / fps)))
    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=loop,
        disposal=2,
        optimize=True,
    )
    return output


_EXAMPLES = """
examples:
  uv run main.py gif.make_gif frames/
  uv run main.py gif.make_gif frames/ --output loop.gif --fps 24
  uv run main.py gif.make_gif scenes/ --width 480 --loop 0
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = ScriptoriumParser(
        description=DESCRIPTION,
        prog="uv run main.py gif.make_gif",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Directory of images (bare name resolves to gif/inputs/)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        metavar="PATH",
        help="Output file or directory (default: timestamp-named in outputs/gif/)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=12,
        help="Frames per second (default: 12)",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        metavar="PX",
        help="Resize frames to this width in pixels; aspect ratio preserved",
    )
    parser.add_argument(
        "--loop",
        type=int,
        default=0,
        help="Loop count, 0 = infinite (default: 0)",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to generate()."""
    args = get_parser().parse_args()

    source = args.source
    if source.parent == Path("."):
        source = _inputs() / source.name

    output = resolve_output(args.output, theme="gif", ext=".gif")

    try:
        result = generate(source, output, fps=args.fps, width=args.width, loop=args.loop)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"wrote {result}")
    sys.exit(0)
