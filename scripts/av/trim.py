"""CLI and programmatic interface for trimming media files."""

import argparse
from pathlib import Path
import sys

from core.argparse import ScriptoriumParser
from scripts.av._utils import av_inputs_dir, av_outputs_dir, run_ffmpeg

TITLE = "Trim the media file that's just too damn long"
DESCRIPTION = "Cut a video or audio file by skipping ahead to a start point, optionally stopping at an end point."

_TRIM_SUBDIR = "trim"
_TRIMMED_SUFFIX = "_trimmed"


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
    args = ["-i", str(input), "-ss", start]
    if end is not None:
        args += ["-to", end]
    args += ["-c", "copy", str(output)]
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
        type=Path,
        default=None,
        metavar="PATH",
        help=f"Destination path; defaults to outputs/av/{_TRIM_SUBDIR}/<input>{_TRIMMED_SUFFIX}<ext>",
    )
    return parser


def _resolve_output(arg: Path | None, input_file: Path) -> Path:
    default_dir = av_outputs_dir() / _TRIM_SUBDIR
    if arg is None:
        return default_dir / f"{input_file.stem}{_TRIMMED_SUFFIX}{input_file.suffix}"
    if arg.parent == Path("."):
        return default_dir / arg.name
    return arg


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to trim()."""
    args = get_parser().parse_args()

    input_file = args.input
    if input_file.parent == Path("."):
        input_file = av_inputs_dir() / input_file.name

    output = _resolve_output(args.output, input_file)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        trim(input_file, output, start=args.start, end=args.end)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    print(output)
    sys.exit(0)
