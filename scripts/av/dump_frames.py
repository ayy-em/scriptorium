"""CLI and programmatic interface for dumping all frames from a video clip."""

import argparse
from pathlib import Path
import re
import sys

from scripts.av._utils import av_inputs_dir, av_outputs_dir, run_ffmpeg

TITLE = "Dump all frames from a video clip"
DESCRIPTION = (
    "Extract every frame between two timestamps to JPEG files. Timestamps must be in NmNs format (e.g. 1m30s, 0m45s)."
)


def parse_timestamp(ts: str) -> float:
    """Parse a NmNs timestamp string to total seconds.

    Args:
        ts: Timestamp in NmNs format, e.g. "1m30s" or "0m45s".

    Returns:
        Total duration in seconds.

    Raises:
        ValueError: If the string does not match NmNs.
    """
    match = re.fullmatch(r"(\d+)m(\d+)s", ts)
    if not match:
        raise ValueError(f"Invalid timestamp {ts!r}. Expected NmNs format (e.g. 1m30s)")
    return float(int(match.group(1)) * 60 + int(match.group(2)))


def dump_frames(video: Path, start: str, end: str, outputs_dir: Path) -> list[Path]:
    """Extract every frame between start and end timestamps from a video.

    Uses frame-accurate seeking (-ss/-to after -i) so all frames in the range
    are captured without keyframe drift. Output files are named frame_00001.jpg,
    frame_00002.jpg, … inside outputs_dir/frames/<video_stem>/<start>-<end>/.

    Args:
        video: Source video file.
        start: Start timestamp in NmNs format (e.g. "1m30s").
        end: End timestamp in NmNs format (e.g. "2m45s").
        outputs_dir: Root output directory.

    Returns:
        Sorted list of extracted JPEG frame paths.

    Raises:
        ValueError: If timestamps are malformed or start >= end.
        subprocess.CalledProcessError: If ffmpeg fails.
    """
    start_secs = parse_timestamp(start)
    end_secs = parse_timestamp(end)

    if start_secs >= end_secs:
        raise ValueError(f"start ({start}) must be before end ({end})")

    frame_dir = outputs_dir / "frames" / video.stem / f"{start}-{end}"
    frame_dir.mkdir(parents=True, exist_ok=True)

    pattern = str(frame_dir / "frame_%05d.jpg")
    run_ffmpeg(["-i", str(video), "-ss", str(start_secs), "-to", str(end_secs), "-vsync", "0", pattern])

    return sorted(frame_dir.glob("*.jpg"))


_EXAMPLES = """
examples:
  uv run main.py av.dump_frames video.mp4 1m30s 2m0s
  uv run main.py av.dump_frames video.mp4 0m0s 0m10s --outputs path/to/out/
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
    parser.add_argument("start", metavar="START", help="Start timestamp (NmNs, e.g. 1m30s)")
    parser.add_argument("end", metavar="END", help="End timestamp (NmNs, e.g. 2m45s)")
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
