"""CLI and programmatic interface for cropping video edges."""

import argparse
from pathlib import Path
import sys

from scripts.av._utils import av_inputs_dir, av_outputs_dir, probe_streams, run_ffmpeg

TITLE = "Crop a video by trimming its edges"
DESCRIPTION = "Remove pixels from the top, right, bottom, and/or left edges of a video file."


def crop(
    source: Path,
    output: Path,
    *,
    top: int,
    right: int,
    bottom: int,
    left: int,
) -> None:
    """Crop a video by removing pixels from its edges.

    Uses ffmpeg's crop filter: ``crop=in_w-left-right:in_h-top-bottom:left:top``.
    The source video dimensions are probed first to validate that the crop values
    leave a positive-sized output frame.

    Args:
        source: Source video file.
        output: Destination file path.
        top: Pixels to remove from the top edge.
        right: Pixels to remove from the right edge.
        bottom: Pixels to remove from the bottom edge.
        left: Pixels to remove from the left edge.

    Raises:
        ValueError: If all crop values are zero, any are negative, or the
            resulting dimensions are not positive, or the source has no video stream.
        subprocess.CalledProcessError: If ffmpeg fails.
    """
    if top == 0 and right == 0 and bottom == 0 and left == 0:
        raise ValueError("All crop values are zero — nothing to crop")
    for name, val in [("top", top), ("right", right), ("bottom", bottom), ("left", left)]:
        if val < 0:
            raise ValueError(f"{name} must be non-negative, got {val}")

    streams = probe_streams(source)
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video_stream is None:
        raise ValueError(f"No video stream found in {source}")

    src_w = int(video_stream["width"])
    src_h = int(video_stream["height"])
    out_w = src_w - left - right
    out_h = src_h - top - bottom

    if out_w <= 0:
        raise ValueError(
            f"Horizontal crop ({left} + {right} = {left + right}) "
            f"exceeds source width ({src_w})"
        )
    if out_h <= 0:
        raise ValueError(
            f"Vertical crop ({top} + {bottom} = {top + bottom}) "
            f"exceeds source height ({src_h})"
        )

    crop_filter = f"crop={out_w}:{out_h}:{left}:{top}"
    run_ffmpeg(["-i", str(source), "-vf", crop_filter, str(output)])


_EXAMPLES = """
examples:
  uv run main.py av.video_crop video.mp4 240 640 240 640
  uv run main.py av.video_crop video.mp4 100 0 100 0
  uv run main.py av.video_crop video.mp4 0 200 0 200 --output cropped.mp4
"""


def _non_negative_int(value: str) -> int:
    """Argparse type that accepts only non-negative integers.

    Args:
        value: Raw string from the command line.

    Returns:
        Parsed non-negative integer.

    Raises:
        argparse.ArgumentTypeError: If the value is not a non-negative integer.
    """
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected integer, got {value!r}")
    if n < 0:
        raise argparse.ArgumentTypeError(f"expected non-negative integer, got {n}")
    return n


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py av.video_crop",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source", type=Path, help="Source video file (bare name resolves to av/inputs/)"
    )
    parser.add_argument(
        "top", type=_non_negative_int, help="Pixels to remove from the top edge"
    )
    parser.add_argument(
        "right", type=_non_negative_int, help="Pixels to remove from the right edge"
    )
    parser.add_argument(
        "bottom", type=_non_negative_int, help="Pixels to remove from the bottom edge"
    )
    parser.add_argument(
        "left", type=_non_negative_int, help="Pixels to remove from the left edge"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="PATH",
        help="Destination file (default: av/outputs/video_crop/<source_name>)",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to crop()."""
    args = get_parser().parse_args()

    source = args.source
    if source.parent == Path("."):
        source = av_inputs_dir() / source.name

    output = args.output
    if output is None:
        crop_out = av_outputs_dir() / "video_crop"
        crop_out.mkdir(parents=True, exist_ok=True)
        output = crop_out / source.name
    elif output.parent == Path("."):
        crop_out = av_outputs_dir() / "video_crop"
        crop_out.mkdir(parents=True, exist_ok=True)
        output = crop_out / output.name

    try:
        crop(source, output, top=args.top, right=args.right, bottom=args.bottom, left=args.left)
        print(f"Written: {output}")
        sys.exit(0)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
