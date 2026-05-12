"""CLI and programmatic interface for extracting frames from videos."""

import argparse
from pathlib import Path
import sys

from scripts.av._utils import av_inputs_dir, av_outputs_dir, run_ffmpeg, run_ffprobe

TITLE = "Extract frames from video(s)"
DESCRIPTION = "Extract N evenly-distributed frames from a video (or directory of videos) as JPEG."

_VIDEO_EXTS = frozenset({".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".m4v"})


def extract_frames(source: Path, count: int, outputs_dir: Path) -> list[Path]:
    """Extract evenly-spaced frames from a video or directory of videos.

    Frames are saved as JPEG to outputs_dir/frames/<video_stem>/frame_001.jpg …
    When count=1, the midpoint frame is extracted.
    Directory input processes each video non-recursively.

    Args:
        source: Video file or directory of video files.
        count: Number of frames to extract per video. Must be >= 1.
        outputs_dir: Root output directory; a frames/<stem>/ subdirectory is created per video.

    Returns:
        List of all extracted JPEG frame paths.

    Raises:
        ValueError: If count < 1.
        FileNotFoundError: If source is a directory with no video files.
        subprocess.CalledProcessError: If ffmpeg fails.
    """
    if count < 1:
        raise ValueError(f"count must be >= 1, got {count}")

    if source.is_dir():
        files = sorted(p for p in source.iterdir() if p.suffix.lower() in _VIDEO_EXTS)
        if not files:
            raise FileNotFoundError(f"No video files found in {source}")
        all_frames: list[Path] = []
        for f in files:
            all_frames.extend(_extract_from_file(f, count, outputs_dir))
        return all_frames

    return _extract_from_file(source, count, outputs_dir)


def _extract_from_file(video: Path, count: int, outputs_dir: Path) -> list[Path]:
    """Extract `count` evenly-spaced frames from a single video file.

    Args:
        video: Source video file.
        count: Number of frames to extract.
        outputs_dir: Root output directory.

    Returns:
        List of extracted JPEG frame paths.
    """
    duration = _get_video_duration(video)
    frame_dir = outputs_dir / "frames" / video.stem
    frame_dir.mkdir(parents=True, exist_ok=True)

    if count == 1:
        seek_times = [duration / 2]
    else:
        step = duration / (count + 1)
        seek_times = [step * (i + 1) for i in range(count)]

    frames: list[Path] = []
    for i, seek in enumerate(seek_times):
        out = frame_dir / f"frame_{i + 1:03d}.jpg"
        # -ss before -i enables fast keyframe seek; -frames:v 1 grabs a single frame.
        run_ffmpeg(["-ss", f"{seek:.3f}", "-i", str(video), "-frames:v", "1", str(out)])
        frames.append(out)

    return frames


def _get_video_duration(file: Path) -> float:
    """Return the duration in seconds of a video file via ffprobe.

    Args:
        file: Video file to probe.

    Returns:
        Duration in seconds.

    Raises:
        ValueError: If ffprobe cannot determine the duration.
    """
    data = run_ffprobe(["-show_format", str(file)])
    duration = data.get("format", {}).get("duration")
    if duration is None:
        raise ValueError(f"Cannot determine duration of {file}")
    return float(duration)


_EXAMPLES = """
examples:
  uv run main.py av.extract_frames video.mp4 --count 5
  uv run main.py av.extract_frames clips/ --count 1
  uv run main.py av.extract_frames video.mp4 --count 10 --outputs path/to/out/
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py av.extract_frames",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source", type=Path, help="Video file or directory of videos (bare name resolves to av/inputs/)"
    )
    parser.add_argument(
        "--count",
        type=int,
        required=True,
        metavar="N",
        help="Number of frames to extract per video",
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        default=None,
        metavar="DIR",
        help="Output root directory (default: av/outputs/); frames go into frames/<stem>/",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to extract_frames()."""
    args = get_parser().parse_args()

    source = args.source
    if source.parent == Path("."):
        source = av_inputs_dir() / source.name

    outputs_dir = args.outputs or av_outputs_dir()

    try:
        frames = extract_frames(source, args.count, outputs_dir)
        for f in frames:
            print(f)
        sys.exit(0)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
