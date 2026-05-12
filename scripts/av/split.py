"""CLI and programmatic interface for splitting media files into segments."""

import argparse
from pathlib import Path
import sys

from scripts.av._utils import av_inputs_dir, av_outputs_dir, run_ffmpeg

TITLE = "Split media file"
DESCRIPTION = "Split a media file at one or more timestamp breakpoints into numbered segments."


def split(input: Path, timestamps: list[str], outputs_dir: Path) -> list[Path]:
    """Split a media file at given timestamps into N+1 numbered segments.

    Segments are stream-copied (no re-encoding) and named
    <stem>_001.<ext>, <stem>_002.<ext>, etc.

    Args:
        input: Source media file.
        timestamps: One or more split points as HH:MM:SS or seconds strings.
        outputs_dir: Directory where segments are written.

    Returns:
        List of output segment paths in order.

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails on any segment.
    """
    outputs_dir.mkdir(parents=True, exist_ok=True)
    breakpoints: list[str | None] = [None, *timestamps, None]
    segments: list[Path] = []

    for i in range(len(breakpoints) - 1):
        start = breakpoints[i]
        end = breakpoints[i + 1]
        output = outputs_dir / f"{input.stem}_{i + 1:03d}{input.suffix}"
        segments.append(output)

        args = ["-i", str(input)]
        if start is not None:
            args += ["-ss", start]
        if end is not None:
            args += ["-to", end]
        args += ["-c", "copy", str(output)]

        run_ffmpeg(args)

    return segments


_EXAMPLES = """
examples:
  uv run main.py av.split video.mp4 00:01:00
  uv run main.py av.split video.mp4 00:01:00 00:02:00 00:03:00
  uv run main.py av.split podcast.mp3 30:00 60:00 --outputs path/to/out/
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py av.split",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", type=Path, help="Source media file (bare name resolves to av/inputs/)")
    parser.add_argument(
        "timestamps",
        nargs="+",
        metavar="TIME",
        help="Split timestamps (HH:MM:SS or seconds); produces N+1 segments",
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        default=None,
        metavar="DIR",
        help="Output directory (default: av/outputs/)",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to split()."""
    args = get_parser().parse_args()

    input_file = args.input
    if input_file.parent == Path("."):
        input_file = av_inputs_dir() / input_file.name

    outputs_dir = args.outputs or av_outputs_dir()

    try:
        segments = split(input_file, args.timestamps, outputs_dir)
        for s in segments:
            print(s)
        sys.exit(0)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
