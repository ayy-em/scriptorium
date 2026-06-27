"""CLI and programmatic interface for splitting media files into segments."""

import argparse
from pathlib import Path
import sys

from core.argparse import ScriptoriumParser
from core.outputs import default_stem, resolve_output_dir
from scripts.av._utils import av_inputs_dir, run_ffmpeg

TITLE = "Split media file in multiple segments"
DESCRIPTION = "Split a media file at one or more timestamp breakpoints into numbered segments."
ACCEPTS: set[str] = {"video", "audio"}


def split(input: Path, timestamps: list[str], outputs_dir: Path, stem: str | None = None) -> list[Path]:
    """Split a media file at given timestamps into N+1 numbered segments.

    Segments are stream-copied (no re-encoding) and named
    <stem>_001.<ext>, <stem>_002.<ext>, etc.

    Args:
        input: Source media file.
        timestamps: One or more split points as HH:MM:SS or seconds strings.
        outputs_dir: Directory where segments are written.
        stem: Filename stem for segments (default: YYYYMMDD_HHmm timestamp).

    Returns:
        List of output segment paths in order.

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails on any segment.
    """
    outputs_dir.mkdir(parents=True, exist_ok=True)
    stem = stem or default_stem()
    breakpoints: list[str | None] = [None, *timestamps, None]
    segments: list[Path] = []

    for i in range(len(breakpoints) - 1):
        start = breakpoints[i]
        end = breakpoints[i + 1]
        output = outputs_dir / f"{stem}_{i + 1:03d}{input.suffix}"
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
  uv run main.py av.split video.mp4 1:00                    # split at 1m
  uv run main.py av.split video.mp4 00:23                   # split at 23s
  uv run main.py av.split video.mp4 1:00 2:00 3:00          # 4 segments
  uv run main.py av.split podcast.mp3 30:00 60:00 --output path/to/out/
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = ScriptoriumParser(
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
        help="Split timestamps (HH:MM:SS, MM:SS, or seconds); produces N+1 segments",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        metavar="PATH",
        help="Output file or directory (default: timestamp-named in outputs/av/)",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to split()."""
    args = get_parser().parse_args()

    input_file = args.input
    if input_file.parent == Path("."):
        input_file = av_inputs_dir() / input_file.name

    out_dir = resolve_output_dir(args.output, theme="av")

    try:
        segments = split(input_file, args.timestamps, out_dir)
        for s in segments:
            print(s)
        sys.exit(0)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
