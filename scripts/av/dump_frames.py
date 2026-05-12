"""CLI and programmatic interface for dumping all frames from a video clip."""

import argparse
from pathlib import Path
import re
import sys

from scripts.av._utils import av_inputs_dir, av_outputs_dir, run_ffmpeg

TITLE = "Dump all frames from a video clip"
DESCRIPTION = "Extract every frame between two timestamps to JPEG files."


def _normalize_timestamp(ts: str) -> str:
    """Accept any ffmpeg-compatible timestamp, plus the legacy NmNs shorthand.

    Supported formats: HH:MM:SS, MM:SS, bare seconds, NmNs (e.g. 1m30s).
    Returns a string safe to pass directly to ffmpeg -ss/-to.
    """
    match = re.fullmatch(r"(\d+)m(\d+)s", ts)
    if match:
        return str(int(match.group(1)) * 60 + int(match.group(2)))
    return ts


def dump_frames(video: Path, start: str, end: str, outputs_dir: Path) -> list[Path]:
    """Extract every frame between start and end timestamps from a video.

    Uses frame-accurate seeking (-ss/-to after -i) so all frames in the range
    are captured without keyframe drift. Output files are named frame_00001.jpg,
    frame_00002.jpg, ... inside outputs_dir/frames/<video_stem>/<start>-<end>/.

    Timestamps are passed directly to ffmpeg and accept any format it understands:
    HH:MM:SS, MM:SS, bare seconds, or the legacy NmNs shorthand (e.g. 1m30s).

    Returns:
        Sorted list of extracted JPEG frame paths.
    """
    ss = _normalize_timestamp(start)
    to = _normalize_timestamp(end)

    safe_label = f"{start}-{end}".replace(":", ".")
    frame_dir = outputs_dir / "frames" / video.stem / safe_label
    frame_dir.mkdir(parents=True, exist_ok=True)

    pattern = str(frame_dir / "frame_%05d.jpg")
    run_ffmpeg(["-i", str(video), "-ss", ss, "-to", to, "-vsync", "0", pattern])

    return sorted(frame_dir.glob("*.jpg"))


_EXAMPLES = """
examples:
  uv run main.py av.dump_frames video.mp4 01:30 02:00
  uv run main.py av.dump_frames video.mp4 0:00 0:10
  uv run main.py av.dump_frames video.mp4 1m30s 2m0s
  uv run main.py av.dump_frames video.mp4 90 120 --outputs path/to/out/
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py av.dump_frames",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("video", type=Path, help="Source video file (bare name resolves to av/inputs/)")
    parser.add_argument("start", metavar="START", help="Start timestamp (e.g. 01:30, 1m30s, 90)")
    parser.add_argument("end", metavar="END", help="End timestamp (e.g. 02:00, 2m0s, 120)")
    parser.add_argument(
        "--outputs",
        type=Path,
        default=None,
        metavar="DIR",
        help="Output root directory (default: av/outputs/); frames go into frames/<stem>/<start>-<end>/",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to dump_frames()."""
    args = get_parser().parse_args()

    video = args.video
    if video.parent == Path("."):
        video = av_inputs_dir() / video.name

    outputs_dir = args.outputs or av_outputs_dir()

    try:
        frames = dump_frames(video, args.start, args.end, outputs_dir)
        dest = frames[0].parent if frames else outputs_dir
        print(f"{len(frames)} frame(s) written to {dest}")
        sys.exit(0)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
