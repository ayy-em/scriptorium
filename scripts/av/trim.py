"""CLI and programmatic interface for trimming media files."""

import argparse
from pathlib import Path
import sys

from scripts.av._utils import run_ffmpeg

TITLE = "Trim media file"
DESCRIPTION = "Cut a video or audio file to a start/end timestamp, or trim the first N seconds."


def trim(
    input: Path,
    output: Path,
    *,
    start: str = "0",
    end: str | None = None,
    seconds: float | None = None,
) -> None:
    """Trim a media file by time range or leading duration.

    Exactly one of `end` or `seconds` must be provided. `seconds` is
    incompatible with both `start` and `end`.

    Args:
        input: Source media file.
        output: Destination file path.
        start: Start time (HH:MM:SS or seconds float string). Ignored with seconds.
        end: End time (HH:MM:SS or seconds float string). Mutually exclusive with seconds.
        seconds: Trim the first N seconds from the beginning. Mutually exclusive with start/end.

    Raises:
        ValueError: If seconds is combined with end or start, or if neither is given.
        subprocess.CalledProcessError: If ffmpeg fails.
    """
    if seconds is not None and end is not None:
        raise ValueError("--seconds and --end are mutually exclusive")
    if seconds is not None and start != "0":
        raise ValueError("--seconds and --start are mutually exclusive")
    if seconds is None and end is None:
        raise ValueError("Provide either --end TIME or --seconds N")

    if seconds is not None:
        args = ["-i", str(input), "-t", str(seconds), "-c", "copy", str(output)]
    else:
        args = ["-i", str(input), "-ss", start, "-to", end, "-c", "copy", str(output)]

    run_ffmpeg(args)


_EXAMPLES = """
examples:
  uv run main.py av.trim input.mp4 output.mp4 --start 00:00:10 --end 00:00:30
  uv run main.py av.trim input.mp4 output.mp4 --end 1:45
  uv run main.py av.trim podcast.mp3 clip.mp3 --seconds 60
"""


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to trim()."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py av.trim",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", type=Path, help="Source media file")
    parser.add_argument("output", type=Path, help="Destination file")
    parser.add_argument(
        "--start",
        default="0",
        metavar="TIME",
        help="Start time (HH:MM:SS or seconds); ignored with --seconds",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--end", metavar="TIME", help="End time (HH:MM:SS or seconds)")
    group.add_argument("--seconds", type=float, metavar="N", help="Trim the first N seconds")
    args = parser.parse_args()

    try:
        trim(args.input, args.output, start=args.start, end=args.end, seconds=args.seconds)
        sys.exit(0)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
