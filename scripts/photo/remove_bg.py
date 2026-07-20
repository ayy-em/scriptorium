"""Remove background from images, producing PNGs with alpha transparency."""

import argparse
from pathlib import Path
import sys
from typing import Any

from PIL import Image

from core.argparse import ScriptoriumParser
from core.outputs import deduplicate, default_stem, resolve_output, resolve_output_dir
from core.paths import inputs_dir, move_to_past_inputs
from scripts.formats._utils import IMAGE_EXTS, find_files

TITLE = "Remove background"
DESCRIPTION = "Remove image backgrounds using AI, outputting transparent PNGs."
ACCEPTS: set[str] = {"image"}

_THEME = "photo"

MODELS = [
    "u2net",
    "u2netp",
    "u2net_human_seg",
    "isnet-general-use",
    "isnet-anime",
    "silueta",
    "birefnet-general",
    "birefnet-general-lite",
    "birefnet-portrait",
    "bria-rmbg",
]

DEFAULT_MODEL = "u2net"


def hex_to_rgba(value: str) -> tuple[int, int, int, int]:
    """Parse a hex color string into an RGBA tuple for rembg's bgcolor option.

    Accepts 3-digit shorthand ("#fff"), 6-digit ("#ffffff") and 8-digit
    with alpha ("#ffffffff") forms, with or without the leading "#".

    Args:
        value: Hex color string, e.g. "#ffffff".

    Returns:
        Tuple of (red, green, blue, alpha) integers in the 0-255 range.

    Raises:
        ValueError: If the string is not a valid hex color.
    """
    digits = value.strip().lstrip("#")
    if len(digits) == 3:  # noqa: PLR2004
        digits = "".join(c * 2 for c in digits)
    if len(digits) == 6:  # noqa: PLR2004
        digits += "ff"
    if len(digits) != 8:  # noqa: PLR2004
        raise ValueError(f"invalid hex color: {value!r} (expected #rgb, #rrggbb or #rrggbbaa)")
    try:
        channels = tuple(int(digits[i : i + 2], 16) for i in range(0, 8, 2))
    except ValueError:
        raise ValueError(f"invalid hex color: {value!r} (non-hex characters)") from None
    return channels  # type: ignore[return-value]


def remove_bg(  # noqa: PLR0913
    source: Path,
    output: Path,
    *,
    model: str = DEFAULT_MODEL,
    alpha_matting: bool = False,
    alpha_matting_foreground_threshold: int = 240,
    alpha_matting_background_threshold: int = 10,
    alpha_matting_erode_size: int = 10,
    only_mask: bool = False,
    post_process_mask: bool = False,
    bgcolor: tuple[int, int, int, int] | None = None,
    session: Any = None,
) -> None:
    """Remove the background from a single image and save as PNG.

    Args:
        source: Path to the input image.
        output: Path for the output PNG file.
        model: Name of the rembg segmentation model to use.
        alpha_matting: Refine edges with alpha matting for soft boundaries.
        alpha_matting_foreground_threshold: Confidence (0-255) above which
            pixels are treated as solid foreground during matting.
        alpha_matting_background_threshold: Confidence (0-255) below which
            pixels are treated as definite background during matting.
        alpha_matting_erode_size: Width in pixels of the uncertain edge band
            that matting blends between foreground and background.
        only_mask: Save the black-and-white segmentation mask instead of
            the cutout image.
        post_process_mask: Clean up noise and jagged edges in the mask.
        bgcolor: Optional RGBA fill for the removed background; None keeps
            the background transparent.
        session: Pre-built rembg session to reuse (batch mode); when None a
            session is created from ``model``.
    """
    from rembg import new_session, remove  # noqa: PLC0415

    if session is None:
        session = new_session(model)

    img = Image.open(source)
    result = remove(
        img,
        session=session,
        alpha_matting=alpha_matting,
        alpha_matting_foreground_threshold=alpha_matting_foreground_threshold,
        alpha_matting_background_threshold=alpha_matting_background_threshold,
        alpha_matting_erode_size=alpha_matting_erode_size,
        only_mask=only_mask,
        post_process_mask=post_process_mask,
        bgcolor=bgcolor,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output, format="PNG")


def remove_bg_batch(  # noqa: PLR0913
    source: Path,
    outputs_dir: Path,
    *,
    model: str = DEFAULT_MODEL,
    alpha_matting: bool = False,
    alpha_matting_foreground_threshold: int = 240,
    alpha_matting_background_threshold: int = 10,
    alpha_matting_erode_size: int = 10,
    only_mask: bool = False,
    post_process_mask: bool = False,
    bgcolor: tuple[int, int, int, int] | None = None,
) -> list[Path]:
    """Remove backgrounds from a single image or all images in a directory.

    The segmentation model is loaded once and reused for every image.
    Successfully processed files that live inside the shared inputs/
    directory are archived to inputs/processed/ afterwards.

    Args:
        source: Source image file or directory of images.
        outputs_dir: Directory where output PNGs are written.
        model: Name of the rembg segmentation model to use.
        alpha_matting: Refine edges with alpha matting for soft boundaries.
        alpha_matting_foreground_threshold: Confidence (0-255) above which
            pixels are treated as solid foreground during matting.
        alpha_matting_background_threshold: Confidence (0-255) below which
            pixels are treated as definite background during matting.
        alpha_matting_erode_size: Width in pixels of the uncertain edge band
            that matting blends between foreground and background.
        only_mask: Save the black-and-white segmentation mask instead of
            the cutout image.
        post_process_mask: Clean up noise and jagged edges in the mask.
        bgcolor: Optional RGBA fill for the removed background; None keeps
            the background transparent.

    Returns:
        List of successfully created output paths.

    Raises:
        FileNotFoundError: If the source path does not exist.
        RuntimeError: If any files fail in batch mode.
    """
    if not source.exists():
        raise FileNotFoundError(f"source not found: {source}")

    from rembg import new_session  # noqa: PLC0415

    session = new_session(model)
    removal_options = {
        "alpha_matting": alpha_matting,
        "alpha_matting_foreground_threshold": alpha_matting_foreground_threshold,
        "alpha_matting_background_threshold": alpha_matting_background_threshold,
        "alpha_matting_erode_size": alpha_matting_erode_size,
        "only_mask": only_mask,
        "post_process_mask": post_process_mask,
        "bgcolor": bgcolor,
    }

    outputs_dir.mkdir(parents=True, exist_ok=True)
    stamp = default_stem()

    if source.is_file():
        output = deduplicate(outputs_dir / f"{stamp}.png")
        remove_bg(source, output, session=session, **removal_options)
        move_to_past_inputs(_THEME, source)
        return [output]

    files = find_files(source, IMAGE_EXTS)
    if not files:
        return []

    successes: list[Path] = []
    failures: list[str] = []

    for i, f in enumerate(files, 1):
        output = deduplicate(outputs_dir / f"{stamp}_{i:03d}.png")
        try:
            remove_bg(f, output, session=session, **removal_options)
            successes.append(output)
            move_to_past_inputs(_THEME, f)
        except Exception as e:
            failures.append(f"{f.name}: {e}")

    if failures:
        bullet_list = "\n".join(f"  - {msg}" for msg in failures)
        raise RuntimeError(f"{len(failures)} of {len(files)} file(s) failed:\n{bullet_list}")

    return successes


_EXAMPLES = """
examples:
  uv run main.py photo.remove_bg
  uv run main.py photo.remove_bg portrait.jpg
  uv run main.py photo.remove_bg photos/ -o cleaned/
  uv run main.py photo.remove_bg portrait.jpg --model birefnet-portrait --alpha-matting
  uv run main.py photo.remove_bg product.png --bgcolor "#ffffff"
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
        nargs="?",
        help="Source image file or directory of images (default: inputs/)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        metavar="PATH",
        help="Output file or directory (default: outputs/photo/)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        choices=MODELS,
        ui_label="AI model",
        help=(
            "Segmentation model: u2net is the general-purpose default; u2netp/silueta are "
            "faster and lighter; u2net_human_seg and birefnet-portrait specialize in people; "
            "isnet-anime for illustrations; birefnet-general and bria-rmbg give the highest "
            "quality but are slower. Non-default models download weights on first use."
        ),
    )
    parser.add_argument(
        "--alpha-matting",
        action="store_true",
        ui_label="Alpha matting",
        help=(
            "Refine edges with alpha matting — better results for soft boundaries like hair, "
            "fur or foliage, at the cost of slower processing."
        ),
    )
    parser.add_argument(
        "--alpha-matting-foreground-threshold",
        type=int,
        default=240,
        metavar="0-255",
        ui_label="Foreground threshold",
        help=(
            "Only used with alpha matting. Confidence (0-255) above which a pixel is kept as "
            "solid foreground; lower values keep more of the edge region."
        ),
    )
    parser.add_argument(
        "--alpha-matting-background-threshold",
        type=int,
        default=10,
        metavar="0-255",
        ui_label="Background threshold",
        help=(
            "Only used with alpha matting. Confidence (0-255) below which a pixel is fully "
            "removed as background; higher values remove more of the edge region."
        ),
    )
    parser.add_argument(
        "--alpha-matting-erode-size",
        type=int,
        default=10,
        metavar="PIXELS",
        ui_label="Erode size",
        help=(
            "Only used with alpha matting. Width in pixels of the uncertain band around edges "
            "that gets smoothly blended; larger values give softer transitions."
        ),
    )
    parser.add_argument(
        "--only-mask",
        action="store_true",
        ui_label="Mask only",
        help=(
            "Output the black-and-white segmentation mask (white = kept subject, "
            "black = removed background) instead of the cutout image."
        ),
    )
    parser.add_argument(
        "--post-process-mask",
        action="store_true",
        ui_label="Post-process mask",
        help="Clean up the segmentation mask, reducing noise and jagged or fuzzy edges.",
    )
    parser.add_argument(
        "--bgcolor",
        type=hex_to_rgba,
        default=None,
        metavar="HEX",
        ui_label="Background color",
        help=(
            "Fill the removed background with a solid color instead of transparency, "
            "e.g. #ffffff for white. Accepts #rgb, #rrggbb or #rrggbbaa."
        ),
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to remove_bg_batch()."""
    args = get_parser().parse_args()

    removal_options = {
        "model": args.model,
        "alpha_matting": args.alpha_matting,
        "alpha_matting_foreground_threshold": args.alpha_matting_foreground_threshold,
        "alpha_matting_background_threshold": args.alpha_matting_background_threshold,
        "alpha_matting_erode_size": args.alpha_matting_erode_size,
        "only_mask": args.only_mask,
        "post_process_mask": args.post_process_mask,
        "bgcolor": args.bgcolor,
    }

    source = args.source if args.source is not None else inputs_dir(_THEME)

    if source.is_file():
        out = resolve_output(args.output, theme=_THEME, ext=".png")
        try:
            remove_bg(source, out, **removal_options)
            move_to_past_inputs(_THEME, source)
            print(out)
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        out_dir = resolve_output_dir(args.output, theme=_THEME)
        try:
            outputs = remove_bg_batch(source, out_dir, **removal_options)
            for o in outputs:
                print(o)
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(1)
