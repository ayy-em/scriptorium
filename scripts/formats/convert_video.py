"""CLI and programmatic interface for converting video files between formats."""

import argparse
from pathlib import Path
import sys

from scripts.av._utils import run_ffmpeg
from scripts.formats._utils import (
    QUALITY_PRESETS,
    VIDEO_EXTS,
    BatchConvertError,
    formats_inputs_dir,
    formats_outputs_dir,
    run_convert,
)

TITLE = "Convert video"
DESCRIPTION = "Transcode video files to a different container or codec."

_VIDEO_OUT_FORMATS = ["mp4", "mkv", "mov", "avi", "webm"]


def _transcode(input_path: Path, output: Path, quality: str, no_audio: bool) -> None:
    """Build and run the ffmpeg transcode command for a single video file.

    Args:
        input_path: Source file.
        output: Destination file.
        quality: Quality preset key.
        no_audio: If True, strip audio from the output.
    """
    preset = QUALITY_PRESETS[quality]
    args = ["-i", str(input_path), "-crf", preset["crf"], "-b:a", preset["audio_bitrate"]]
    if no_audio:
        args.append("-an")
    args.append(str(output))
    run_ffmpeg(args)


def convert(
    source: Path,
    to_format: str,
    outputs_dir: Path,
    *,
    quality: str = "medium",
    no_audio: bool = False,
) -> list[Path]:
    """Transcode a single video file or a directory of video files to a target format.

    Args:
        source: Source video file or directory of video files.
        to_format: Target container extension without leading dot (e.g. "mp4", "mkv").
        outputs_dir: Directory where transcoded files are written.
        quality: One of "low", "medium", "high", "max". Defaults to "medium".
        no_audio: Strip audio from the output. Defaults to False.

    Returns:
        List of successfully created output Paths.

    Raises:
        ValueError: If quality is not a recognised preset.
        subprocess.CalledProcessError: If ffmpeg fails in single-file mode.
        BatchConvertError: If any files fail in batch mode (after processing all).
    """
    if quality not in QUALITY_PRESETS:
        raise ValueError(f"Unknown quality {quality!r}. Choose from: {', '.join(QUALITY_PRESETS)}")

    def _fn(inp: Path, out: Path) -> None:
        _transcode(inp, out, quality, no_audio)

    return run_convert(source, VIDEO_EXTS, outputs_dir, to_format, _fn)


_EXAMPLES = """
examples:
  uv run main.py formats.convert_video clip.avi --to mp4
  uv run main.py formats.convert_video --to mp4 --quality high
  uv run main.py formats.convert_video clips/ --to webm --no-audio
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py formats.convert_video",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source",
        type=Path,
        nargs="?",
        help="Source file or directory (default: formats/inputs/)",
    )
    parser.add_argument(
        "--to",
        required=True,
        dest="to_format",
        metavar="FORMAT",
        choices=_VIDEO_OUT_FORMATS,
        help="Target format",
    )
    parser.add_argument(
        "--quality",
        default="medium",
        choices=list(QUALITY_PRESETS),
        help="Quality preset (default: medium). max = CRF 0 (lossless H.264).",
    )
    parser.add_argument(
        "--no-audio",
        action="store_true",
        help="Strip audio track from the output.",
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        default=None,
        metavar="DIR",
        help="Output directory (default: formats/outputs/)",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to convert()."""
    args = get_parser().parse_args()
    source = args.source or formats_inputs_dir()
    out_dir = args.outputs or formats_outputs_dir()

    try:
        outputs = convert(source, args.to_format, out_dir, quality=args.quality, no_audio=args.no_audio)
        for o in outputs:
            print(o)
        sys.exit(0)
    except BatchConvertError as e:
        for o in e.succeeded:
            print(o)
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
