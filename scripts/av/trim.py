"""CLI and programmatic interface for trimming media files."""

import argparse
from pathlib import Path
import sys

from core.argparse import ScriptoriumParser
from core.outputs import resolve_output
from core.paths import move_to_past_inputs, resolve_input
from scripts.av._utils import (
    copy_would_land_on,
    format_time,
    has_video_stream,
    parse_time,
    probe_duration_or_none,
    run_ffmpeg_with_progress,
)

TITLE = "Trim the media file that's just too damn long"
DESCRIPTION = "Cut a video or audio file by skipping ahead to a start point, optionally stopping at an end point."
ACCEPTS: set[str] = {"video", "audio"}
TEMPLATE = "scripts/av/trim.html"

# What to do when the requested start does not fall on a keyframe.
MODE_AUTO = "auto"
MODE_FAST = "fast"
MODE_PRECISE = "precise"
TRIM_MODES = (MODE_AUTO, MODE_FAST, MODE_PRECISE)

# Quality of the re-encode, on the scale ffmpeg's encoders share. 18 is
# visually lossless for x264 and matches what formats.convert_video calls
# "high" — a trim should not be the step that costs you quality you notice.
_REENCODE_CRF = "18"


def _should_reencode(input: Path, start_seconds: float, mode: str) -> tuple[bool, float | None]:
    """Decide whether this cut needs a re-encode to land where the user asked.

    Args:
        input: Source media file.
        start_seconds: Requested start position in seconds.
        mode: One of ``TRIM_MODES``.

    Returns:
        ``(reencode, keyframe)`` — whether to re-encode, and where a stream copy
        would have started (None when that is unknown or irrelevant).

    Raises:
        ValueError: If *mode* is not a recognised trim mode.
    """
    if mode not in TRIM_MODES:
        raise ValueError(f"Unknown trim mode {mode!r}. Choose from: {', '.join(TRIM_MODES)}")
    if mode == MODE_FAST:
        return False, None
    if mode == MODE_PRECISE:
        return True, None
    accurate, keyframe = copy_would_land_on(input, start_seconds)
    return not accurate, keyframe


def trim(
    input: Path,
    output: Path,
    start: str,
    end: str | None = None,
    mode: str = MODE_AUTO,
) -> str:
    """Trim a media file by time range.

    A stream copy cannot begin mid-GOP, so ``-ss`` seeks backwards to the
    nearest keyframe. On a sparsely-keyed source — a long GOP, a low frame
    rate, a screen recording — that can be seconds away from the requested cut,
    and trimming the first few seconds off such a file used to report success
    while handing back something indistinguishable from the original. The
    default now checks where a copy would actually land and re-encodes when
    that is not where the user asked for.

    Args:
        input: Source media file.
        output: Destination file path.
        start: Start time (HH:MM:SS, MM:SS, or seconds). Output begins here.
        end: Optional end time in the same formats; when omitted, the output
            runs to the source's end.
        mode: ``"auto"`` (default) re-encodes only when a copy would miss the
            requested start; ``"fast"`` always stream-copies, accepting the
            keyframe snap; ``"precise"`` always re-encodes.

    Returns:
        ``"copy"`` or ``"reencode"`` — the strategy actually used.

    Raises:
        ValueError: If *mode* is unrecognised or a timestamp cannot be parsed.
        subprocess.CalledProcessError: If ffmpeg fails.
    """
    start_seconds = parse_time(start)
    reencode, keyframe = _should_reencode(input, start_seconds, mode)

    args = ["-ss", start, "-i", str(input)]
    if end is not None:
        duration = parse_time(end) - parse_time(start)
        args += ["-t", format_time(duration)]
    else:
        source_duration = probe_duration_or_none(input)
        duration = None if source_duration is None else max(0.0, source_duration - start_seconds)

    if reencode:
        # Input seeking stays: modern ffmpeg seeks to the preceding keyframe and
        # then decodes and discards up to the exact point, so the cut is frame
        # accurate without the cost of decoding the whole file. The audio is
        # copied — it has no GOP to be inaccurate about, and the container is
        # the source's own, so its codec is muxable by definition. No video
        # encoder is named for the same reason: ffmpeg's default for this
        # container is muxable into it, which libx264 is not for every one.
        args += ["-c:a", "copy"]
        if has_video_stream(input):
            args += ["-crf", _REENCODE_CRF]
    else:
        args += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
    args.append(str(output))

    if reencode and mode == MODE_AUTO:
        landed = "an unknown position" if keyframe is None else f"{keyframe:.2f}s"
        print(f"Re-encoding: a stream copy would have started at {landed}, not {start_seconds:.2f}s.")

    # ffmpeg reports its position within the output, which for a trim is the
    # length of the kept range rather than of the source.
    run_ffmpeg_with_progress(args, total_seconds=duration)
    return "reencode" if reencode else "copy"


_EXAMPLES = """
examples:
  uv run main.py av.trim input.mp4 00:03                       # skip the first three seconds
  uv run main.py av.trim input.mp4 1:03 5:04                   # keep 1m03s..5m04s
  uv run main.py av.trim input.mp4 1:03 5:04 --output cut.mp4  # custom output filename
  uv run main.py av.trim input.mp4 00:03 --mode fast           # snap to a keyframe, never re-encode
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
        "--mode",
        choices=TRIM_MODES,
        default=MODE_AUTO,
        help=(
            "auto: re-encode only when a stream copy would miss the requested start "
            "(default); fast: always stream-copy, snapping to the nearest keyframe; "
            "precise: always re-encode"
        ),
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
    input_file = resolve_input(input_file, "av")

    output = resolve_output(args.output, theme="av", ext=input_file.suffix)

    try:
        trim(input_file, output, start=args.start, end=args.end, mode=args.mode)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    move_to_past_inputs("av", input_file)
    print(output)
    sys.exit(0)
