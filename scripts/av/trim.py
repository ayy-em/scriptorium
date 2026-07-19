"""CLI and programmatic interface for trimming media files."""

import argparse
from pathlib import Path
import sys

from core.argparse import ScriptoriumParser
from core.outputs import resolve_output
from scripts.av._utils import av_inputs_dir, format_time, parse_time, run_ffmpeg

TITLE = "Trim the media file that's just too damn long"
DESCRIPTION = "Cut a video or audio file by skipping ahead to a start point, optionally stopping at an end point."
ACCEPTS: set[str] = {"video", "audio"}


def trim(input: Path, output: Path, start: str, end: str | None = None) -> None:
    """Trim a media file by time range.

    Args:
        input: Source media file.
        output: Destination file path.
        start: Start time (HH:MM:SS, MM:SS, or seconds). Output begins here.
        end: Optional end time in the same formats; when omitted, the output
            runs to the source's end.

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails.
    """
    args = ["-ss", start, "-i", str(input)]
    if end is not None:
        duration = parse_time(end) - parse_time(start)
        args += ["-t", format_time(duration)]
    args += ["-c", "copy", "-avoid_negative_ts", "make_zero", str(output)]
    run_ffmpeg(args)


_EXAMPLES = """
examples:
  uv run main.py av.trim input.mp4 00:03                       # skip the first three seconds
  uv run main.py av.trim input.mp4 1:03 5:04                   # keep 1m03s..5m04s
  uv run main.py av.trim input.mp4 1:03 5:04 --output cut.mp4  # custom output filename
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = ScriptoriumParser(
        description=DESCRIPTION,
        prog="uv run main.py av.trim",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Source media file (bare name resolves to inputs/)",
    )
    parser.add_argument(
        "start",
        metavar="START",
        help="Start time (HH:MM:SS, MM:SS, or seconds)",
    )
    parser.add_argument(
        "end",
        nargs="?",
        default=None,
        metavar="END",
        help="Optional end time; defaults to end-of-file",
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
    """CLI entrypoint. Parse arguments and dispatch to trim()."""
    args = get_parser().parse_args()

    input_file = args.input
    if input_file.parent == Path("."):
        input_file = av_inputs_dir() / input_file.name

    output = resolve_output(args.output, theme="av", ext=input_file.suffix)

    try:
        trim(input_file, output, start=args.start, end=args.end)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    print(output)
    sys.exit(0)
