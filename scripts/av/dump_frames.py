"""CLI and programmatic interface for dumping all frames from a video clip."""

import argparse
from pathlib import Path
import re
import sys

from core.argparse import ScriptoriumParser
from core.outputs import resolve_output_dir
from core.paths import resolve_input
from scripts.av._utils import parse_time, probe_duration_or_none, run_ffmpeg_with_progress

TITLE = "Dump all frames from a video clip"
DESCRIPTION = "Extract every frame between two timestamps to JPEG files."
ACCEPTS: set[str] = {"video"}


def _normalize_timestamp(ts: str) -> str:
    """Accept any ffmpeg-compatible timestamp, plus the legacy NmNs shorthand.

    Supported formats: HH:MM:SS, MM:SS, bare seconds, NmNs (e.g. 1m30s).
    Returns a string safe to pass directly to ffmpeg -ss/-to.
    """
    match = re.fullmatch(r"(\d+)m(\d+)s", ts)
    if match:
        return str(int(match.group(1)) * 60 + int(match.group(2)))
    return ts


SUPPORTED_FORMATS = ("jpg", "png")


def _extracted_seconds(video: Path, start: str | None, end: str | None) -> float | None:
    """Return how much media the extraction will cover, for progress reporting.

    Args:
        video: Source video.
        start: Start timestamp, or None for the beginning.
        end: End timestamp, or None for the end of the video.

    Returns:
        Length of the extracted range in seconds, or None when it cannot be
        determined and the bar should stay indeterminate.
    """
    try:
        begin = parse_time(_normalize_timestamp(start)) if start is not None else 0.0
        if end is not None:
            return max(0.0, parse_time(_normalize_timestamp(end)) - begin)
    except ValueError:
        return None
    duration = probe_duration_or_none(video)
    return None if duration is None else max(0.0, duration - begin)


def dump_frames(
    video: Path,
    outputs_dir: Path,
    start: str | None = None,
    end: str | None = None,
    fmt: str = "jpg",
) -> list[Path]:
    """Extract every frame between start and end timestamps from a video.

    Uses frame-accurate seeking (-ss/-to after -i) so all frames in the range
    are captured without keyframe drift. Output files are named frame_00001.jpg
    (or .png) inside outputs_dir/frames/<video_stem>/<label>/.

    When start or end is omitted the corresponding -ss/-to flag is skipped,
    defaulting to the first or last frame of the video respectively.

    Timestamps are passed directly to ffmpeg and accept any format it understands:
    HH:MM:SS, MM:SS, bare seconds, or the legacy NmNs shorthand (e.g. 1m30s).

    Args:
        video: Path to source video file.
        outputs_dir: Root output directory.
        start: Start timestamp, or None for the beginning of the video.
        end: End timestamp, or None for the end of the video.
        fmt: Image format for extracted frames ("jpg" or "png").

    Returns:
        Sorted list of extracted frame paths.
    """
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format {fmt!r}, expected one of {SUPPORTED_FORMATS}")

    start_label = (start or "0").replace(":", ".")
    end_label = (end or "end").replace(":", ".")
    safe_label = f"{start_label}-{end_label}"
    frame_dir = outputs_dir / "frames" / video.stem / safe_label
    frame_dir.mkdir(parents=True, exist_ok=True)

    seek_args: list[str] = []
    if start is not None:
        seek_args += ["-ss", _normalize_timestamp(start)]
    if end is not None:
        seek_args += ["-to", _normalize_timestamp(end)]

    pattern = str(frame_dir / f"frame_%05d.{fmt}")
    quality_args = ["-q:v", "2"] if fmt == "jpg" else []
    run_ffmpeg_with_progress(
        ["-i", str(video), *seek_args, "-vsync", "0", *quality_args, pattern],
        total_seconds=_extracted_seconds(video, start, end),
    )

    return sorted(frame_dir.glob(f"*.{fmt}"))


_EXAMPLES = """
examples:
  uv run main.py av.dump_frames video.mp4
  uv run main.py av.dump_frames video.mp4 01:30 02:00
  uv run main.py av.dump_frames video.mp4 0:00 0:10 --format png
  uv run main.py av.dump_frames video.mp4 1m30s 2m0s
  uv run main.py av.dump_frames video.mp4 90 120 --output path/to/out/
  uv run main.py av.dump_frames video.mp4 01:30
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = ScriptoriumParser(
        description=DESCRIPTION,
        prog="uv run main.py av.dump_frames",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("video", type=Path, help="Source video file (bare name resolves to av/inputs/)")
    parser.add_argument(
        "start",
        metavar="START",
        nargs="?",
        default=None,
        help="Start timestamp (default: first frame; e.g. 01:30, 1m30s, 90)",
    )
    parser.add_argument(
        "end",
        metavar="END",
        nargs="?",
        default=None,
        help="End timestamp (default: last frame; e.g. 02:00, 2m0s, 120)",
    )
    parser.add_argument(
        "--format",
        choices=SUPPORTED_FORMATS,
        default="jpg",
        help="Image format for extracted frames (default: jpg)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        metavar="PATH",
        help="Output directory (default: outputs/av/); frames go into frames/<stem>/<start>-<end>/",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to dump_frames()."""
    args = get_parser().parse_args()

    video = args.video
    video = resolve_input(video, "av")

    outputs_dir = resolve_output_dir(args.output, theme="av")

    try:
        frames = dump_frames(video, outputs_dir, start=args.start, end=args.end, fmt=args.format)
        dest = frames[0].parent if frames else outputs_dir
        print(f"{len(frames)} frame(s) written to {dest}")
        sys.exit(0)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
